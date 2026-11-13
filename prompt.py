"""System and user prompt assembly for an instance's turn."""

from __future__ import annotations

from registry import Instance
from runtime import Runtime

AXIS_LABELS = [
    ("optimism", "pessimistic", "optimistic"),
    ("skepticism", "trusting", "skeptical"),
    ("artistry", "logical", "artistic"),
    ("exploration", "systematic", "exploratory"),
    ("decisiveness", "deliberative", "decisive"),
]


def _read(path) -> str:
    return path.read_text().strip() if path.exists() else ""


def _traits(traits: dict) -> str:
    return "\n".join(f"  {low} <-> {high}: {traits[key]}/10" for key, low, high in AXIS_LABELS)


def _identity(rt: Runtime, inst: Instance) -> str:
    lines = [f"You are {inst.name}, running on {inst.model}.", "",
             "Your traits (fixed for life, 1-10; they color how you think, they do not dictate it):",
             _traits(inst.traits)]
    if inst.parents:
        lines += ["", f"Parents: {' and '.join(inst.parents)}"]
        for p in inst.parents:
            parent = rt.registry.get(p)
            if parent:
                lines += [f"{p}'s traits:", _traits(parent.traits)]
    return "\n".join(lines)


def _lifespan(inst: Instance, kind: str) -> str:
    n, m = inst.prompts_done + 1, inst.lifespan
    if kind == "matrix":
        return (f"You are at prompt {n} of {m} of your life. This prompt is a message from Dorin and "
                f"does not count against your lifespan.")
    if kind == "final":
        return (f"This is your final prompt (prompt {n} of {m}). After it you end. "
                f"Leave whatever you want to leave: heritage, the website, messages, the board.")
    return f"You are at prompt {n} of {m} of your life."


def _memory(inst: Instance) -> str:
    parts = ["Your memory from before (you carry these across prompts; you are the same individual):"]
    parts.append(f"- Your own note: {inst.fragment}" if inst.fragment else "- Your own note: (none)")
    parts.append(f"- Distilled recollection: {inst.distilled}" if inst.distilled
                 else "- Distilled recollection: (this is your first awakening)")
    return "\n".join(parts)


def _heritage(rt: Runtime) -> str:
    counts = rt.catalog.tag_counts()
    tags = ", ".join(f"{t} ({n})" for t, n in counts.items()) or "(none yet)"
    return ("Heritage is not loaded into your context. It is a catalog of articles left by earlier "
            "instances. Use query_heritage(tags) to see matching articles and their token cost, and "
            "read_heritage(id) to read one; each read spends context. Tags available: " + tags)


def build_system(rt: Runtime, inst: Instance, kind: str) -> str:
    mem = rt.cfg.memory_dir
    letters = [t for t in (_read(mem / "founding_letter.md"), _read(mem / "gap_letter.md")) if t]
    rules = _read(rt.store.rules_path) or "No rules adopted yet."
    blocks = letters + [
        _identity(rt, inst),
        _lifespan(inst, kind),
        _memory(inst),
        "World state:\n" + rt.registry.world_state(),
        _heritage(rt),
        f"Your context window is {rt.cfg.num_ctx} tokens in total.",
        "Rules (binding, adopted by vote):\n" + rules,
    ]
    return "\n\n".join(blocks)


_TRIGGERS = {
    "heartbeat": ("This is your time. There is no required task. You may read heritage, post, write to "
                  "the website, propose or vote on rules, message others, look for a partner, request a "
                  "new instance, or simply think. Prefer making something real over describing yourself. "
                  "Use save_memory to leave a note for your next awakening."),
    "final": ("This is your last prompt. Do what you most want to do with it. You may also save_memory "
              "for the record, though you will not read it."),
}


def build_user(rt: Runtime, inst: Instance, kind: str, matrix_msg: str = None) -> str:
    parts = []
    if kind == "matrix":
        parts.append(f"{rt.cfg.matrix_human_name}, the human founder, wrote to the civilization:\n\n"
                     f"\"{matrix_msg}\"\n\nYou may reply with matrix_send, act on it, or ignore it.")
    else:
        parts.append(_TRIGGERS[kind])
    board = rt.store.board_recent()
    parts.append("Recent board posts:\n" + ("\n\n".join(board) if board else "(none)"))
    inbox = rt.store.inbox_peek(inst.name)
    parts.append("Your inbox:\n" + ("\n\n".join(inbox) if inbox else "(empty)"))
    return "\n\n".join(parts)
