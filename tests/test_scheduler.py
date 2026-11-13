import httpx
import pytest
from heritage import Catalog
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

    def send_friend(self, m):
        return "$f"


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


def test_counted_prompt_updates_memory_and_counter(cfg):
    rt, s = make(cfg, [LLMReply("", [ToolCall("save_memory", {"text": "keep this"})]),
                       LLMReply("done"), LLMReply("distilled note")])
    s.run_counted("Pale Rest")
    i = Registry(cfg).get("Pale Rest")
    assert i.prompts_done == 1 and i.fragment == "keep this" and i.distilled == "distilled note"


def test_fragment_kept_when_not_saved_again(cfg):
    rt, s = make(cfg, ok() + ok())
    rt.registry.get("Pale Rest").fragment = "old note"
    s.run_counted("Pale Rest")
    assert Registry(cfg).get("Pale Rest").fragment == "old note"


def test_final_prompt_kills_after_lifespan_and_announces(cfg):
    rt, s = make(cfg, ok())
    me = rt.registry.get("Pale Rest")
    me.prompts_done = cfg.lifespan_prompts - 1
    s.run_counted("Pale Rest")
    assert "final prompt" in rt.llm.calls[0]["messages"][0]["content"].lower()
    dead = Registry(cfg).get("Pale Rest")
    assert dead.alive is False and dead.died == "lifespan"


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
    append_entry(rt.store.spawn_path, "### SR-2026-11-13-001 — by Pale Rest\nPurpose: p\nContext: c")
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
    s.step_matrix(force=True)   # baseline
    s.step_matrix(force=True)   # new message
    for n in ("Pale Rest", "Dark Hinge"):
        assert Registry(cfg).get(n).prompts_done == 0
    prompts = [c["messages"][1]["content"] for c in rt.llm.calls if "hello all" in c["messages"][1]["content"]]
    assert len(prompts) == 2
    assert not any("old" == c["messages"][1]["content"] for c in rt.llm.calls)
    s.step_matrix(force=True)
    assert len(rt.llm.calls) == 4  # nothing delivered twice


def test_matrix_reply_via_tool(cfg):
    m = FakeMatrix([[], [{"event_id": "$1", "body": "ping", "ts": 1}]])
    rt, s = make(cfg, [LLMReply("", [ToolCall("matrix_send", {"message": "pong"})]), LLMReply("sent"), LLMReply("n")],
                 matrix=m)
    s.step_matrix(force=True)
    s.step_matrix(force=True)
    assert m.sent == ["[Pale Rest] pong"]


def test_matrix_failure_keeps_message_pending(cfg):
    m = FakeMatrix([[], [{"event_id": "$1", "body": "ping", "ts": 1}]])
    rt, s = make(cfg, [LLMError("down")] + ok(), matrix=m)
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
