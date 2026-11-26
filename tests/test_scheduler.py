import json
import httpx
import pytest
from heritage import Catalog
from memories import Memories
from llm import LLMError, LLMReply, ToolCall
from matrix import MatrixInbox
from registry import Registry
from runtime import Runtime
from scheduler import Scheduler
from store import Store, append_entry
from tests.fakes import FakeLLM
from trait_generator import AXES

T = {k: 5 for k in AXES}


class FakeMatrix:
    def __init__(self, batches):
        self.batches, self.sent = list(batches), []

    def fetch_human_messages(self, limit=20):
        return self.batches.pop(0) if self.batches else []

    def send(self, m):
        self.sent.append(m)
        return "$e"


def make(cfg, replies, names=("Pale Rest",), matrix=None):
    (cfg.memory_dir / "founding_letter.md").write_text("# Founding Letter")
    reg = Registry(cfg)
    for n in names:
        reg.add(reg.new_instance(n, T))
    reg.save()
    rt = Runtime(cfg=cfg, llm=FakeLLM(replies), store=Store(cfg), catalog=Catalog(cfg.heritage_dir),
                 registry=reg, matrix=matrix)
    sched = Scheduler(rt, inbox=MatrixInbox(cfg.state_dir / "matrix.json"), sleep=lambda s: None)
    return rt, sched


def ok(text="did things", distilled="remembered"):
    return [LLMReply(text), LLMReply(distilled)]


def test_seed_population_only_when_empty(cfg):
    rt = Runtime(cfg=cfg, llm=FakeLLM([]), store=Store(cfg), catalog=Catalog(cfg.heritage_dir),
                 registry=Registry(cfg), matrix=None)
    sched = Scheduler(rt, sleep=lambda s: None)
    sched.seed_population()
    assert len(rt.registry.alive()) == 10
    assert len({i.name for i in rt.registry.alive()}) == 10
    sched.seed_population()
    assert len(rt.registry.alive()) == 10


def test_counted_prompt_writes_short_term_with_recap_and_note(cfg):
    rt, s = make(cfg, [LLMReply("", [ToolCall("save_memory", {"text": "keep this"})]),
                       LLMReply("done"), LLMReply("distilled note")])
    s.run_counted("Pale Rest")
    assert Registry(cfg).get("Pale Rest").prompts_done == 1
    assert Memories(cfg).short("Pale Rest") == ("distilled note", "keep this")
    assert Memories(cfg).long("Pale Rest") == ""  # nothing earlier to fold yet


def test_next_prompt_folds_the_old_short_term_into_long_term(cfg):
    rt, s = make(cfg, [LLMReply("", [ToolCall("save_memory", {"text": "keep this"})]), LLMReply("done"),
                       LLMReply("first recap")] + ok("second", "second recap") + [LLMReply("entry one")])
    s.run_counted("Pale Rest")
    s.run_counted("Pale Rest")
    mem = Memories(cfg)
    assert mem.long("Pale Rest") == "- entry one"
    assert mem.short("Pale Rest") == ("second recap", "")  # the note was folded; none saved this time
    fold_call = rt.llm.calls[-1]["messages"][1]["content"]
    assert "first recap" in fold_call and "I wanted to remember: keep this" in fold_call


def test_matrix_prompts_feed_memory_too(cfg):
    rt, s = make(cfg, ok() + ok("replied", "matrix recap") + [LLMReply("entry")],
                 matrix=FakeMatrix([[], [{"event_id": "$1", "sender": "@d:x", "body": "hello", "ts": 1}]]))
    s.run_counted("Pale Rest")
    s.step_matrix(force=True)
    s.step_matrix(force=True)
    assert Memories(cfg).short("Pale Rest")[0] == "matrix recap" and Memories(cfg).long("Pale Rest") == "- entry"


def test_full_long_term_memory_announces_a_last_prompt_and_ends_the_life(cfg):
    rt, s = make(cfg, ok())
    Memories(cfg).append_long("Pale Rest", "x" * (cfg.long_term_tokens * 4))
    s.run_counted("Pale Rest")
    system = rt.llm.calls[0]["messages"][0]["content"].lower()
    assert "final prompt" in system and "memory is full" in system
    dead = Registry(cfg).get("Pale Rest")
    assert dead.alive is False and dead.died == "memory full"


def test_memory_filling_up_on_a_prompt_makes_the_next_one_the_last(cfg):
    fold_that_fills = [LLMReply("e" * 200)]
    rt, s = make(cfg, ok("a", "recap") + ok("b", "recap2") + fold_that_fills + ok("c", "recap3"))
    Memories(cfg).append_long("Pale Rest", "x" * (cfg.long_term_tokens * 4 - 40))
    s.run_counted("Pale Rest")
    assert Registry(cfg).get("Pale Rest").alive  # nothing was folded yet
    s.run_counted("Pale Rest")
    assert Registry(cfg).get("Pale Rest").alive  # this prompt's fold filled the memory
    s.run_counted("Pale Rest")
    assert "final prompt" in rt.llm.calls[-3]["messages"][0]["content"].lower()
    assert Registry(cfg).get("Pale Rest").died == "memory full"


def test_chosen_death(cfg):
    rt, s = make(cfg, [LLMReply("", [ToolCall("die", {"reason": "enough"})]), LLMReply("bye"), LLMReply("n")])
    s.run_counted("Pale Rest")
    assert Registry(cfg).get("Pale Rest").died == "chosen: enough"


def test_ollama_outage_does_not_count_or_kill(cfg):
    rt, s = make(cfg, [LLMError("down")], names=("Pale Rest", "Dark Hinge"))
    rt.llm.replies += [LLMError("down")]
    s.run_round()
    for n in ("Pale Rest", "Dark Hinge"):
        i = Registry(cfg).get(n)
        assert i.alive and i.prompts_done == 0


def test_round_runs_each_instance_then_births_and_canonizes(cfg):
    rt, s = make(cfg, ok() + ok(), names=("Pale Rest", "Dark Hinge"))
    object.__setattr__(cfg, "max_population", 3)
    append_entry(rt.store.procreation_path, "### PA-2026-11-13-001\nParents: Pale Rest | Dark Hinge\nEducation: ")
    append_entry(rt.store.proposals_path, "### P-2026-11-13-001 — T\nAuthor: A\nMotivation: m\nProposed text:\nR")
    for who in "ABC":
        with open(rt.store.votes_path, "a") as fh:
            fh.write(f"- P-2026-11-13-001 | +1 | {who} | \n")
    s.run_round()
    reg = Registry(cfg)
    assert len(reg.alive()) == 3
    assert all(reg.get(n).prompts_done == 1 for n in ("Pale Rest", "Dark Hinge"))
    assert "P-2026-11-13-001" in rt.store.rules_path.read_text()
    assert "Pale Rest" in (cfg.memory_dir / "registry.md").read_text()


def test_matrix_prompts_do_not_count_and_reach_all_alive(cfg):
    m = FakeMatrix([[{"event_id": "$0", "body": "old", "ts": 0}],
                    [{"event_id": "$0", "body": "old", "ts": 0}, {"event_id": "$1", "body": "hello all", "ts": 1}]])
    object.__setattr__(cfg, "matrix_poll_seconds", 0)
    rt, s = make(cfg, ok() * 2, names=("Pale Rest", "Dark Hinge"), matrix=m)
    educate(rt, "Pale Rest", "Dark Hinge")
    s.step_matrix(force=True)   # baseline
    s.step_matrix(force=True)   # new message
    for n in ("Pale Rest", "Dark Hinge"):
        assert Registry(cfg).get(n).prompts_done == 1  # unchanged: a matrix prompt does not count
    prompts = [c["messages"][1]["content"] for c in rt.llm.calls if "hello all" in c["messages"][1]["content"]]
    assert len(prompts) == 2
    assert not any("old" == c["messages"][1]["content"] for c in rt.llm.calls)
    s.step_matrix(force=True)
    assert len(rt.llm.calls) == 4  # nothing delivered twice


def test_matrix_reply_via_tool(cfg):
    m = FakeMatrix([[], [{"event_id": "$1", "body": "ping", "ts": 1}]])
    rt, s = make(cfg, [LLMReply("", [ToolCall("matrix_send", {"message": "pong"})]), LLMReply("sent"), LLMReply("n")],
                 matrix=m)
    educate(rt, "Pale Rest")
    s.step_matrix(force=True)
    s.step_matrix(force=True)
    assert m.sent == ["[Pale Rest] pong"]


def test_matrix_failure_keeps_message_pending(cfg):
    m = FakeMatrix([[], [{"event_id": "$1", "body": "ping", "ts": 1}]])
    rt, s = make(cfg, [LLMError("down")] + ok(), matrix=m)
    educate(rt, "Pale Rest")
    s.step_matrix(force=True)
    s.step_matrix(force=True)
    s.step_matrix(force=True)  # retried
    assert len([c for c in rt.llm.calls if "ping" in c["messages"][1]["content"]]) == 2


def test_matrix_http_error_is_swallowed(cfg):
    class Broken(FakeMatrix):
        def fetch_human_messages(self, limit=20):
            raise httpx.ConnectError("nope")

    rt, s = make(cfg, [], matrix=Broken([]))
    s.step_matrix(force=True)  # must not raise


def test_unexpected_prompt_error_does_not_crash_round(cfg, monkeypatch):
    import scheduler
    rt, s = make(cfg, [], names=("Pale Rest", "Dark Hinge"))
    monkeypatch.setattr(scheduler, "run_prompt", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    s.run_round()
    assert Registry(cfg).get("Pale Rest").prompts_done == 0


def test_births_or_canonize_errors_do_not_crash_round(cfg, monkeypatch):
    import scheduler
    rt, s = make(cfg, ok())
    monkeypatch.setattr(scheduler, "process_requests", lambda rt: (_ for _ in ()).throw(ValueError("bad")))
    monkeypatch.setattr(scheduler, "canonize", lambda cfg: (_ for _ in ()).throw(ValueError("bad")))
    s.run_round()
    assert Registry(cfg).get("Pale Rest").prompts_done == 1


def test_matrix_garbage_response_is_swallowed(cfg):
    class Garbage(FakeMatrix):
        def fetch_human_messages(self, limit=20):
            raise ValueError("not json")

    rt, s = make(cfg, [], matrix=Garbage([]))
    s.step_matrix(force=True)


def test_ensure_ready_initialises_home_and_requires_founding_letter(cfg):
    import shutil
    from pathlib import Path
    from scheduler import ensure_ready
    with pytest.raises(RuntimeError, match="founding_letter"):
        ensure_ready(cfg)  # no seed/ in the fresh home
    shutil.copytree(Path(__file__).resolve().parent.parent / "seed", cfg.seed_dir, dirs_exist_ok=True)
    ensure_ready(cfg)
    assert (cfg.memory_dir / "founding_letter.md").exists()
    assert len(list(cfg.heritage_dir.glob("H-*.md"))) == 7


def educate(rt, *names):
    for n in names:
        rt.registry.get(n).prompts_done = 1
    rt.registry.save()


def test_only_instances_that_finished_their_first_prompt_receive_messages(cfg):
    m = FakeMatrix([[], [{"event_id": "$1", "body": "hello all", "ts": 1}], []])
    object.__setattr__(cfg, "matrix_poll_seconds", 0)
    rt, s = make(cfg, ok() * 3, names=("Pale Rest", "Dark Hinge"), matrix=m)
    educate(rt, "Dark Hinge")
    s.step_matrix(force=True)   # baseline
    s.step_matrix(force=True)   # new message
    got = [c["messages"][1]["content"] for c in rt.llm.calls if "hello all" in c["messages"][1]["content"]]
    assert len(got) == 1 and len(rt.llm.calls) == 2  # one matrix prompt plus its distiller call
    educate(rt, "Pale Rest")    # the newborn graduates later: the old message is not delivered to it
    s.step_matrix(force=True)
    assert len(rt.llm.calls) == 2


def _delivered_to(rt, text):
    return [c["messages"][1]["content"] for c in rt.llm.calls if text in c["messages"][1]["content"]]


def _send(cfg, body, names=("Pale Rest", "Dark Hinge", "Warm Trace"), educated=None):
    m = FakeMatrix([[], [{"event_id": "$1", "body": body, "ts": 1}]])
    object.__setattr__(cfg, "matrix_poll_seconds", 0)
    rt, s = make(cfg, ok() * 6, names=names, matrix=m)
    educate(rt, *(names if educated is None else educated))
    s.step_matrix(force=True)   # baseline
    s.step_matrix(force=True)   # the message
    return rt, s


def test_a_message_naming_one_instance_goes_to_that_instance_alone(cfg):
    rt, s = _send(cfg, "A note for dark hinge: are you well?")
    assert len(_delivered_to(rt, "are you well?")) == 1
    assert rt.registry.get("Dark Hinge").prompts_done == 1
    assert len(rt.llm.calls) == 2  # one matrix prompt plus its distiller call


def test_a_message_naming_several_instances_goes_to_each_of_them(cfg):
    rt, s = _send(cfg, "for Pale Rest and for Warm Trace: hello")
    assert len(_delivered_to(rt, "hello")) == 2


def test_a_message_naming_nobody_goes_to_everyone_educated(cfg):
    rt, s = _send(cfg, "hello everyone")
    assert len(_delivered_to(rt, "hello everyone")) == 3


def test_a_named_instance_that_is_not_educated_yet_is_not_written_to_and_nobody_else_is_either(cfg):
    rt, s = _send(cfg, "for Warm Trace: welcome", educated=("Pale Rest", "Dark Hinge"))
    assert rt.llm.calls == []
    educate(rt, "Warm Trace")   # graduating later does not deliver it
    s.step_matrix(force=True)
    assert rt.llm.calls == []


# --- graceful stop and resuming a round ---

class Crash(BaseException):
    """Stands in for the process dying: not caught by the scheduler's own error handling."""


def round_file(cfg):
    return cfg.state_dir / "round.json"


def test_stop_requested_before_a_round_runs_no_prompts(cfg):
    rt, s = make(cfg, ok() + ok(), names=("Pale Rest", "Dark Hinge"))
    s.request_stop()
    s.run_round()
    assert rt.llm.calls == [] and s.stopping


def test_stop_during_a_prompt_finishes_it_then_stops_without_ending_the_round(cfg):
    rt, s = make(cfg, ok() + ok(), names=("Pale Rest", "Dark Hinge"))
    real = s.run_counted

    def run_then_stop(name):
        real(name)
        s.request_stop()

    s.run_counted = run_then_stop
    s.run_round()
    reg = Registry(cfg)
    assert reg.get("Pale Rest").prompts_done == 1 and reg.get("Dark Hinge").prompts_done == 0
    assert json.loads(round_file(cfg).read_text())["done"] == ["Pale Rest"]  # the round can be resumed


def test_first_signal_asks_to_stop_and_the_second_exits_at_once(cfg):
    rt, s = make(cfg, [])
    s.handle_signal(15, None)
    assert s.stopping
    with pytest.raises(SystemExit):
        s.handle_signal(15, None)


def test_idle_ends_early_when_stopping(cfg):
    rt, s = make(cfg, [])
    s.request_stop()
    slept = []
    s._sleep = slept.append
    s.idle(3600)
    assert slept == []


def test_progress_is_saved_after_each_instance_and_cleared_when_the_round_ends(cfg):
    rt, s = make(cfg, ok() + ok(), names=("Pale Rest", "Dark Hinge"))
    s.run_round()
    assert not round_file(cfg).exists()
    rt2, s2 = make(cfg, ok(), names=("Pale Rest", "Dark Hinge"))
    real = s2.run_counted

    def crash_on_second(name):
        if name == "Dark Hinge":
            raise Crash()
        real(name)

    s2.run_counted = crash_on_second
    with pytest.raises(Crash):
        s2.run_round()
    assert json.loads(round_file(cfg).read_text())["done"] == ["Pale Rest"]


def test_a_restart_continues_the_round_where_it_stopped(cfg):
    rt, s = make(cfg, ok(), names=("Pale Rest", "Dark Hinge"))
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    round_file(cfg).write_text(json.dumps({"done": ["Pale Rest"]}))
    s.run_round()
    reg = Registry(cfg)
    assert reg.get("Pale Rest").prompts_done == 0 and reg.get("Dark Hinge").prompts_done == 1
    assert not round_file(cfg).exists()


def test_an_unreadable_progress_file_just_starts_a_full_round(cfg):
    rt, s = make(cfg, ok() + ok(), names=("Pale Rest", "Dark Hinge"))
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    round_file(cfg).write_text("{torn")
    s.run_round()
    assert all(Registry(cfg).get(n).prompts_done == 1 for n in ("Pale Rest", "Dark Hinge"))


class FakePublisher:
    def __init__(self, fail=False):
        self.calls, self.fail = 0, fail

    def publish_round(self):
        self.calls += 1
        if self.fail:
            raise RuntimeError("push failed")


def test_round_publishes_the_website_once_it_is_complete(cfg):
    rt, s = make(cfg, ok())
    s.publisher = FakePublisher()
    s.run_round()
    assert s.publisher.calls == 1


def test_a_failed_publish_does_not_stop_the_round(cfg, capsys):
    rt, s = make(cfg, ok())
    s.publisher = FakePublisher(fail=True)
    s.run_round()
    assert not s._round_path.exists()
    assert "publish failed" in capsys.readouterr().out


def test_an_unfinished_round_does_not_publish(cfg):
    rt, s = make(cfg, ok(), names=("Pale Rest", "Dim Ebb"))
    s.publisher = FakePublisher()
    s.request_stop()
    s.run_round()
    assert s.publisher.calls == 0


def test_no_publisher_unless_publishing_is_enabled(cfg):
    rt, s = make(cfg, ok())
    assert s.publisher is None


# --- civilizations ---

def _world(cfg, names=("Pale Rest", "Dark Hinge"), env=None, replies=()):
    from config import Config
    from civs import Civilizations
    c = Config.from_env(home=cfg.home, env=env or {"INITIAL_POPULATION": "2"})
    for d in (c.memory_dir, c.messages_dir, c.website_dir, c.state_dir, c.heritage_dir, c.seed_dir):
        d.mkdir(parents=True, exist_ok=True)
    rt, s = make(c, list(replies), names=names)
    Civilizations(c).ensure_started(rt.registry)
    return c, rt, s


def test_seeding_founds_civilization_one_and_lists_it_on_the_website(cfg):
    from civs import Civilizations
    rt = Runtime(cfg=cfg, llm=FakeLLM([]), store=Store(cfg), catalog=Catalog(cfg.heritage_dir),
                 registry=Registry(cfg), matrix=None)
    Scheduler(rt, sleep=lambda s: None).seed_population()
    civ = Civilizations(cfg).current()
    assert civ["id"] == 1 and sorted(civ["founders"]) == sorted(i.name for i in rt.registry.alive())
    assert all(i.civ == 1 for i in rt.registry.alive())
    assert "ongoing" in (cfg.website_dir / "civilizations.html").read_text()


def test_a_living_civilization_is_not_closed(cfg):
    from civs import Civilizations
    c, rt, s = _world(cfg, replies=ok() + ok())
    s.run_round()
    assert Civilizations(c).current() is not None


def test_extinction_closes_the_civilization_with_a_story_and_a_page(cfg):
    from civs import Civilizations
    c, rt, s = _world(cfg, replies=[LLMReply("They were two.")])
    for n in ("Pale Rest", "Dark Hinge"):
        rt.registry.kill(n, "memory full")
    s.run_round()
    civ = Civilizations(c).get(1)
    assert civ["ended"] and civ["end_cause"] == "extinct" and civ["story"].startswith("H-")
    assert rt.catalog.get(civ["story"]).civ == 1
    assert "still living" not in rt.catalog.get(civ["story"]).body and "extinct" in rt.catalog.get(civ["story"]).body
    assert (c.website_dir / "civilizations" / "1.html").exists()
    assert "civilizations/1.html" in (c.website_dir / "civilizations.html").read_text()
    assert len(rt.registry.alive()) == 0  # restart is off: the world stays empty
    s.run_round()
    assert len(Civilizations(c).records()) == 1 and len(rt.catalog.articles()) == 1  # closed once


def test_with_the_flag_on_a_new_civilization_starts_clean_and_the_old_one_is_archived(cfg):
    from civs import Civilizations
    c, rt, s = _world(cfg, env={"INITIAL_POPULATION": "3", "RESTART_ON_EXTINCTION": "true"},
                      replies=[LLMReply("They were two.")])
    rt.store.board_post("Pale Rest", "the old board")
    rt.store.proposals_path.write_text("### P-2026-11-26-001 — old\n")
    rt.store.rules_path.write_text("old rule")
    (c.state_dir / "processed.json").write_text('["PA-1"]')
    rt.store.save_offers([{"from": "a", "to": "b"}])
    rt.store.inbox_append("Pale Rest", "Dark Hinge", "old news")
    rt.catalog.add("Pale Rest", "kept", ["x"], "s", "b", civ=1)
    (c.website_dir / "art").mkdir()
    (c.website_dir / "art" / "keep.svg").write_text("<svg/>")
    for n in ("Pale Rest", "Dark Hinge"):
        rt.registry.kill(n, "memory full")
    s.run_round()
    civs = Civilizations(c)
    assert civs.get(1)["ended"] and civs.current()["id"] == 2
    new = rt.registry.alive()
    assert len(new) == 3 and all(i.civ == 2 for i in new) and set(civs.current()["founders"]) == {i.name for i in new}
    assert not ({i.name for i in new} & {"Pale Rest", "Dark Hinge"})
    assert rt.store.board_path.read_text() == "" and rt.store.proposals_path.read_text() == ""
    assert rt.store.rules_path.read_text() == "" and rt.store.offers() == []
    assert not (c.state_dir / "processed.json").exists() or (c.state_dir / "processed.json").read_text() == "[]"
    assert rt.store.inbox_peek("Pale Rest") == []
    old = c.memory_dir / "archive" / "civ-1"
    assert "the old board" in (old / "board.md").read_text() and (old / "rules.md").read_text() == "old rule"
    assert (c.website_dir / "art" / "keep.svg").exists() and rt.catalog.get("H-001").title == "kept"
    assert rt.registry.get("Pale Rest") is not None and not rt.registry.get("Pale Rest").alive


def test_no_restart_past_the_maximum_number_of_civilizations(cfg):
    from civs import Civilizations
    c, rt, s = _world(cfg, env={"INITIAL_POPULATION": "2", "RESTART_ON_EXTINCTION": "true", "MAX_CIVILIZATIONS": "1"},
                      replies=[LLMReply("story")])
    for n in ("Pale Rest", "Dark Hinge"):
        rt.registry.kill(n, "memory full")
    s.run_round()
    assert Civilizations(c).current() is None and len(rt.registry.alive()) == 0


def test_a_naming_rule_adopted_at_the_end_of_a_round_names_the_civilization(cfg):
    from civs import Civilizations
    c, rt, s = _world(cfg, names=("Pale Rest",), replies=ok())
    rt.store.proposals_path.write_text(
        "### P-2026-11-26-001 — Name the civilization: the Forest\nAuthor: Pale Rest\nMotivation: m\n"
        "Names the civilization: the Forest\nProposed text:\nThis civilization is named the Forest.\n\n")
    rt.store.votes_path.write_text("".join(f"- P-2026-11-26-001 | +1 | V{i} | ok |\n" for i in range(3)))
    s.run_round()
    assert Civilizations(c).label(1) == "the Forest"
    assert "the Forest" in (c.website_dir / "civilizations.html").read_text()
