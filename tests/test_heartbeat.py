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
