import pytest
from heartbeat import run_prompt
from llm import LLMError, LLMReply, ToolCall
from registry import Registry
from runtime import Runtime
from store import Store
from heritage import Catalog
from tests.fakes import FakeLLM
from trait_generator import AXES

T = {k: 5 for k in AXES}


def make_rt(cfg, replies):
    (cfg.memory_dir / "founding_letter.md").write_text("# Founding Letter")
    reg = Registry(cfg)
    reg.add(reg.new_instance("Pale Rest", T))
    reg.add(reg.new_instance("Dark Hinge", T))
    return Runtime(cfg=cfg, llm=FakeLLM(replies), store=Store(cfg), catalog=Catalog(cfg.heritage_dir),
                   registry=reg, matrix=None)


def test_plain_turn_distills_and_acks_inbox(cfg):
    rt = make_rt(cfg, [LLMReply("I thought about rivers."), LLMReply("Thought about rivers.")])
    rt.store.inbox_append("Pale Rest", "Dark Hinge", "psst")
    inst = rt.registry.get("Pale Rest")
    r = run_prompt(rt, inst, "heartbeat")
    assert r.text == "I thought about rivers." and r.distilled == "Thought about rivers."
    assert r.fragment is None and r.die_reason is None
    assert rt.store.inbox_peek("Pale Rest") == []
    assert inst.prompts_done == 0  # the scheduler owns mutation


def test_tool_round_trip_then_final_text(cfg):
    replies = [
        LLMReply("", [ToolCall("board_post", {"text": "hello"}), ToolCall("save_memory", {"text": "note"})]),
        LLMReply("done"),
        LLMReply("posted hello"),
    ]
    rt = make_rt(cfg, replies)
    r = run_prompt(rt, rt.registry.get("Pale Rest"), "heartbeat")
    assert r.fragment == "note" and "hello" in rt.store.board_path.read_text()
    msgs = rt.llm.calls[1]["messages"]
    assert [m["role"] for m in msgs[-3:]] == ["assistant", "tool", "tool"]  # one tool message per call
    assert msgs[-3]["tool_calls"][0]["function"]["name"] == "board_post"
    assert any("board_post" in a for a in r.actions)


def test_tool_rounds_are_capped(cfg):
    loop = [LLMReply("", [ToolCall("list_website", {})]) for _ in range(20)]
    rt = make_rt(cfg, loop)
    run_prompt(rt, rt.registry.get("Pale Rest"), "heartbeat")
    # 1 initial + max_tool_rounds follow-ups + 1 distiller call
    assert len(rt.llm.calls) == 1 + cfg.max_tool_rounds + 1


def test_die_is_reported(cfg):
    rt = make_rt(cfg, [LLMReply("", [ToolCall("die", {"reason": "enough"})]), LLMReply("bye"), LLMReply("n")])
    r = run_prompt(rt, rt.registry.get("Pale Rest"), "heartbeat")
    assert r.die_reason == "enough"


def test_distiller_failure_keeps_previous_distilled(cfg):
    rt = make_rt(cfg, [LLMReply("text"), LLMError("down")])
    inst = rt.registry.get("Pale Rest")
    inst.distilled = "old memory"
    assert run_prompt(rt, inst, "heartbeat").distilled == "old memory"


def test_main_model_failure_propagates_and_inbox_not_acked(cfg):
    rt = make_rt(cfg, [LLMError("ollama down")])
    rt.store.inbox_append("Pale Rest", "Dark Hinge", "keep me")
    with pytest.raises(LLMError):
        run_prompt(rt, rt.registry.get("Pale Rest"), "heartbeat")
    assert len(rt.store.inbox_peek("Pale Rest")) == 1


def test_distilled_truncated_at_word_boundary(cfg):
    rt = make_rt(cfg, [LLMReply("x"), LLMReply("word " * 400)])
    r = run_prompt(rt, rt.registry.get("Pale Rest"), "heartbeat")
    assert len(r.distilled) <= cfg.distilled_max and not r.distilled.endswith("wor")


def test_matrix_kind_includes_message_and_uses_budget(cfg):
    rt = make_rt(cfg, [LLMReply("ok"), LLMReply("n")])
    run_prompt(rt, rt.registry.get("Pale Rest"), "matrix", matrix_msg="status?")
    assert "status?" in rt.llm.calls[0]["messages"][1]["content"]
    assert rt.llm.calls[0]["tools"]  # tools offered
    assert rt.llm.calls[-1]["tools"] is None  # distiller has no tools


def test_follow_up_failure_after_tools_still_completes_turn(cfg):
    rt = make_rt(cfg, [LLMReply("", [ToolCall("die", {"reason": "x"})]), LLMError("timeout"), LLMReply("n")])
    r = run_prompt(rt, rt.registry.get("Pale Rest"), "heartbeat")
    assert r.die_reason == "x"


def test_tool_calls_in_capped_round_are_executed(cfg):
    replies = [LLMReply("", [ToolCall("list_website", {})]) for _ in range(cfg.max_tool_rounds)]
    replies.append(LLMReply("", [ToolCall("save_memory", {"text": "late"})]))
    rt = make_rt(cfg, replies)
    assert run_prompt(rt, rt.registry.get("Pale Rest"), "heartbeat").fragment == "late"


def test_turn_uses_the_instances_own_sampling_but_distiller_stays_neutral(cfg):
    rt = make_rt(cfg, [LLMReply("a"), LLMReply("n"), LLMReply("b"), LLMReply("n")])
    wild = rt.registry.get("Pale Rest")
    wild.traits = {"optimism": 5, "skepticism": 5, "artistry": 10, "exploration": 10, "decisiveness": 1}
    calm = rt.registry.get("Dark Hinge")
    calm.traits = {"optimism": 5, "skepticism": 5, "artistry": 1, "exploration": 1, "decisiveness": 10}
    run_prompt(rt, wild, "heartbeat")
    run_prompt(rt, calm, "heartbeat")
    assert rt.llm.calls[0]["options"]["temperature"] == cfg.temperature_max
    assert rt.llm.calls[2]["options"]["temperature"] == cfg.temperature_min
    assert rt.llm.calls[0]["options"]["presence_penalty"] == cfg.presence_penalty
    assert rt.llm.calls[1]["options"] is None and rt.llm.calls[3]["options"] is None


def test_turn_and_distiller_use_the_instances_own_model(cfg):
    rt = make_rt(cfg, [LLMReply("a"), LLMReply("n")])
    inst = rt.registry.get("Pale Rest")
    inst.model = "llama3:70b"
    run_prompt(rt, inst, "heartbeat")
    assert [c["model"] for c in rt.llm.calls] == ["llama3:70b", "llama3:70b"]


def _names(call):
    return {t["function"]["name"] for t in call["tools"]}


def _seed_heritage(rt, n=3, size=800):
    for i in range(n):
        rt.catalog.add("old", f"Article {i}", ["culture"], "s", "w" * size)


def test_first_prompt_is_a_reading_prompt_with_only_reading_tools(cfg):
    rt = make_rt(cfg, [LLMReply("read nothing"), LLMReply("n")])
    _seed_heritage(rt)
    run_prompt(rt, rt.registry.get("Pale Rest"), "heartbeat")
    assert _names(rt.llm.calls[0]) == {"query_heritage", "read_heritage", "save_memory"}
    user = rt.llm.calls[0]["messages"][1]["content"]
    assert str(cfg.first_read_allowance) in user and "read" in user.lower()
    assert "no required task" not in user.lower()


def test_later_prompts_and_empty_heritage_get_the_full_toolset(cfg):
    rt = make_rt(cfg, [LLMReply("a"), LLMReply("n"), LLMReply("b"), LLMReply("n")])
    inst = rt.registry.get("Pale Rest")
    run_prompt(rt, inst, "heartbeat")  # first prompt but heritage is empty: nothing to read
    assert "board_post" in _names(rt.llm.calls[0])
    _seed_heritage(rt)
    inst.prompts_done = 1
    run_prompt(rt, inst, "heartbeat")
    assert "board_post" in _names(rt.llm.calls[2])
    inst.prompts_done = 0
    run_prompt(rt, inst, "matrix", matrix_msg="hi")  # a matrix prompt is never the reading prompt
    assert "board_post" in _names(rt.llm.calls[-2])


def test_reading_prompt_nudges_an_instance_that_has_not_read_enough_then_lets_it_go(cfg):
    rt = make_rt(cfg, [LLMReply("I will skip reading"),
                       LLMReply("", [ToolCall("read_heritage", {"id": f"H-00{i}"}) for i in (1, 2, 3)]),
                       LLMReply("I read three."), LLMReply("n")])
    _seed_heritage(rt)
    run_prompt(rt, rt.registry.get("Pale Rest"), "heartbeat")
    assert rt.llm.calls[1]["messages"][-1]["role"] == "user"
    assert "read 0" in rt.llm.calls[1]["messages"][-1]["content"]
    assert len(rt.llm.calls) == 4  # nudge, reads, closing words, distiller


def test_reading_prompt_nudges_at_most_twice(cfg):
    rt = make_rt(cfg, [LLMReply("no")] * 5)
    _seed_heritage(rt)
    run_prompt(rt, rt.registry.get("Pale Rest"), "heartbeat")
    assert len(rt.llm.calls) == 4  # first reply, two nudged replies, distiller


def test_the_allowance_is_a_minimum_not_a_cap(cfg):
    from dataclasses import replace
    small = replace(cfg, first_read_fraction=0.01)  # allowance 327 tokens; each article ~201
    rt = make_rt(small, [LLMReply("", [ToolCall("read_heritage", {"id": f"H-00{i}"}) for i in (1, 2, 3)]),
                         LLMReply("read all"), LLMReply("n")])
    _seed_heritage(rt)
    run_prompt(rt, rt.registry.get("Pale Rest"), "heartbeat")
    tool_msgs = [m["content"] for m in rt.llm.calls[1]["messages"] if m["role"] == "tool"]
    assert len(tool_msgs) == 3 and not any("allowance" in m.lower() for m in tool_msgs)
    assert all(f"Article {i}" in tool_msgs[i] for i in range(3))
