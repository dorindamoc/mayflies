"""Run one prompt (turn) for one instance."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from budget import ContextBudget, est_tokens
from distiller import distill
from llm import LLMError
from prompt import build_system, build_user
from runtime import Runtime
from tools import ToolContext, TurnOutcome, dispatch, tool_specs


@dataclass
class TurnResult:
    text: str
    actions: list
    fragment: Optional[str]
    die_reason: Optional[str]
    distilled: str


def run_prompt(rt: Runtime, inst, kind: str, matrix_msg: str = None) -> TurnResult:
    cfg = rt.cfg
    system = build_system(rt, inst, kind)
    user = build_user(rt, inst, kind, matrix_msg)
    budget = ContextBudget(cfg.num_ctx, cfg.response_reserve)
    budget.spend(est_tokens(system) + est_tokens(user))
    outcome = TurnOutcome()
    ctx = ToolContext(cfg=cfg, instance=inst, registry=rt.registry, store=rt.store, catalog=rt.catalog,
                      budget=budget, matrix=rt.matrix, outcome=outcome)

    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    specs = tool_specs()
    text = ""
    for round_no in range(cfg.max_tool_rounds + 1):
        reply = rt.llm.chat(messages, tools=specs)
        text = reply.content or text
        if not reply.tool_calls or round_no == cfg.max_tool_rounds:
            break
        messages.append({"role": "assistant", "content": reply.content or "", "tool_calls": [
            {"function": {"name": c.name, "arguments": c.arguments}} for c in reply.tool_calls]})
        for call in reply.tool_calls:
            result = dispatch(ctx, call.name, call.arguments)
            messages.append({"role": "tool", "tool_name": call.name, "content": result})

    rt.store.inbox_ack(inst.name)
    try:
        distilled = distill(rt.llm, cfg, inst, kind, text, outcome.actions) or inst.distilled
    except LLMError:
        distilled = inst.distilled
    return TurnResult(text, outcome.actions, outcome.fragment, outcome.die_reason, distilled)
