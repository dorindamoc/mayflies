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
                      {"role": "user", "content": user}], tools=None, think=False, model=inst.model)
    return _truncate(reply.content, cfg.distilled_max)


COMPACT_SYSTEM = ("You shorten a note that a short-lived mind wrote to itself, because it is over the length limit. "
                  "Keep its first-person voice, its own words where you can, and the points it stressed. Drop "
                  "repetition and detail first. Output only the shortened note, no preamble, at most {words} words.")
COMPACT_TRIES = 3
CHARS_PER_WORD = 6


def compact_note(llm, cfg: Config, inst, text: str) -> str:
    """Rewrite an over-long self-chosen note to fit, asking again with its real length while it is still too long.

    Models count words far better than characters, so the target is in words. Returns the last attempt, which
    may still be over the limit; the caller cuts it then. Raises if the model call fails."""
    limit = cfg.memory_fragment_max
    words = int(limit * 0.8 / CHARS_PER_WORD)
    messages = [{"role": "system", "content": COMPACT_SYSTEM.format(words=words)},
                {"role": "user", "content": text}]
    out = ""
    for attempt in range(COMPACT_TRIES):
        out = llm.chat(messages, tools=None, think=False, model=inst.model).content.strip()
        if len(out) <= limit or attempt == COMPACT_TRIES - 1:
            return out
        messages += [{"role": "assistant", "content": out},
                     {"role": "user", "content": f"That is {len(out)} characters and the limit is {limit}. "
                                                 f"Shorten it to at most {words} words."}]
    return out
