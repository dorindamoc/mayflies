"""A neutral agent that compresses one prompt into a short note for the next awakening."""

from __future__ import annotations

from config import Config

SYSTEM = ("You compress the memory of a short-lived mind. You are given its previous recollection, "
          "its own saved note, and what it just did. Write one compact first-person recollection that "
          "the same mind will read when it wakes next: who it is in this world, what it was doing, what "
          "mattered to it, what it left unfinished. Keep what is important, drop what is not. "
          "Output only the recollection, no preamble, at most {limit} characters.")


def _truncate(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    return cut.rsplit(" ", 1)[0] if " " in cut else cut


def distill(llm, cfg: Config, inst, kind: str, final_text: str, actions: list) -> str:
    acts = "\n".join(f"- {a}" for a in actions) or "(none)"
    user = (f"Previous recollection: {inst.distilled or '(none)'}\n"
            f"Own saved note: {inst.fragment or '(none)'}\n"
            f"Prompt kind: {kind}\n"
            f"Actions taken this prompt:\n{acts}\n"
            f"Final words this prompt:\n{final_text or '(none)'}")
    reply = llm.chat([{"role": "system", "content": SYSTEM.format(limit=cfg.distilled_max)},
                      {"role": "user", "content": user}], tools=None, think=False)
    return _truncate(reply.content, cfg.distilled_max)
