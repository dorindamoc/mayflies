"""Run one prompt (turn) for one instance."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from budget import ContextBudget, est_tokens
from distiller import distill
from llm import LLMError
from prompt import build_system, build_user, is_reading_prompt
from runtime import Runtime
from tools import ToolContext, TurnOutcome, dispatch, tool_specs
from trait_generator import sampling_options


READING_TOOLS = {"query_heritage", "read_heritage", "save_memory"}
MAX_NUDGES = 2


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
                      budget=budget, matrix=rt.matrix, outcome=outcome, llm=rt.llm)

    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    specs = tool_specs(cfg)
    reading = is_reading_prompt(rt, inst, kind)
    nudges = 0
    if reading:
        specs = [s for s in specs if s["function"]["name"] in READING_TOOLS]
        # the allowance is a minimum: read that much, or everything there is if that is less
        wanted = min(cfg.first_read_allowance, sum(a.cost for a in rt.catalog.articles()))
        ctx.heritage_minimum = wanted
    sampling = sampling_options(inst.traits, cfg.temperature_min, cfg.temperature_max, cfg.presence_penalty)
    text = ""
    for round_no in range(cfg.max_tool_rounds + 1):
        try:
            reply = rt.llm.chat(messages, tools=specs, model=inst.model, options=sampling)
        except LLMError:
            if round_no == 0:
                raise  # nothing happened yet: the prompt can be retried whole
            break  # tools already ran: finish the turn rather than replay their side effects
        text = reply.content or text
        if not reply.tool_calls:
            if reading and nudges < MAX_NUDGES and ctx.heritage_read < wanted and round_no < cfg.max_tool_rounds:
                nudges += 1
                messages.append({"role": "assistant", "content": reply.content or ""})
                messages.append({"role": "user", "content": (
                    f"You have read {ctx.heritage_read} tokens of heritage; in this first prompt you are meant to read at "
                    f"least {wanted}. Choose more articles with query_heritage and read_heritage before you finish.")})
                continue
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
