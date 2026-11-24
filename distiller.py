"""A neutral agent that compresses one prompt into a short note for the next awakening."""

from __future__ import annotations

from config import Config
from llm import LLMError

SYSTEM = ("You compress what a short-lived mind just did into a recap it will read when it wakes next. You are "
          "given what it did this prompt and its final words. Write one compact first-person recap: what it was "
          "doing, what mattered to it, what it left unfinished. Keep what is important, drop what is not. "
          "Output only the recap, no preamble, at most {limit} characters.")


def _truncate(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    return cut.rsplit(" ", 1)[0] if " " in cut else cut


def distill(llm, cfg: Config, inst, kind: str, final_text: str, actions: list) -> str:
    """Recap one prompt for the short-term memory."""
    acts = "\n".join(f"- {a}" for a in actions) or "(none)"
    user = (f"Prompt kind: {kind}\n"
            f"Actions taken this prompt:\n{acts}\n"
            f"Final words this prompt:\n{final_text or '(none)'}")
    reply = llm.chat([{"role": "system", "content": SYSTEM.format(limit=cfg.short_term_max)},
                      {"role": "user", "content": user}], tools=None, think=False, model=inst.model)
    return _truncate(reply.content, cfg.short_term_max)


FOLD_SYSTEM = ("You compress the memory of a short-lived mind for its long-term memory. You are given what it "
               "remembered of one earlier prompt, including a note it chose to keep. Write one very compact "
               "first-person entry that keeps only what will still matter much later. "
               "Output only the entry, no preamble, at most {limit} characters.")


def fold(llm, cfg: Config, inst, short_text: str) -> str:
    """Compact a short-term memory into one long-term entry. Never fails: on an error it cuts the text instead."""
    limit = cfg.long_term_entry_max
    try:
        reply = llm.chat([{"role": "system", "content": FOLD_SYSTEM.format(limit=limit)},
                          {"role": "user", "content": short_text}], tools=None, think=False, model=inst.model)
        entry = _truncate(reply.content, limit)
    except LLMError:
        entry = ""
    return entry or _truncate(short_text, limit)


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
