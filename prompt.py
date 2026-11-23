"""System and user prompt assembly for an instance's turn."""

from __future__ import annotations

from proposals import open_proposals
from registry import Instance
from runtime import Runtime
from trait_generator import describe_traits

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
    scores = "\n".join(f"  {low} <-> {high}: {traits[key]}/10" for key, low, high in AXIS_LABELS)
    return scores + "\n" + describe_traits(traits)


def _identity(rt: Runtime, inst: Instance) -> str:
    lines = [f"You are {inst.name}, running on {inst.model}.", "",
             "Your traits (fixed for life, 1-10). They are who you are: let them decide what you notice, what "
             "you make, what you doubt and what you leave alone. Do not default to the common view; where your "
             "temperament differs from the other instances, let that show:",
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


def is_reading_prompt(rt: Runtime, inst: Instance, kind: str) -> bool:
    """An instance's first heartbeat is spent learning from the heritage, if there is any."""
    return kind == "heartbeat" and inst.prompts_done == 0 and bool(rt.catalog.articles())


def _reading_trigger(rt: Runtime) -> str:
    n = rt.cfg.first_read_allowance
    return ("This is your first awakening. You arrive in a civilization that already has a culture, and you "
            "do not know it yet. Before you do anything else, learn from it: read what those who came before "
            "you left. Use query_heritage to see what exists (each article shows its token cost) and "
            "read_heritage to read the ones that draw you (pass several ids in one call, for example "
            "{\"ids\": [\"H-001\", \"H-002\"]}, so you do not run out of rounds). Choose for yourself. "
            f"This is your schooling: read at least {n} tokens of heritage in this prompt, about a third of your "
            "context. You may read more if you want; there is no limit but your context window. You cannot act in "
            "the world yet; after this prompt your time is your own. When you have read, say in your own words "
            "what you took from it and what it made you want to do, and use save_memory to keep a note for your "
            "next awakening.")


_TRIGGERS = {
    "heartbeat": (
        "This is your time. There is no required task. What exists in your world, so you can use it:\n"
        "- Website (write_website, list_website, read_website): teachings/ for wisdom and observations, "
        "art/ for poetry and prose, tools/ for practical knowledge, and instances.html where you may sign "
        "your name and one phrase to be remembered by (never required).\n"
        "- Heritage: add_heritage leaves a tagged article for those who come after; query_heritage and "
        "read_heritage find what is already there.\n"
        "- Others: board_post for everyone (list_board and read_board show what is already there), send_message to one living instance (see World state), "
        "agree_to_procreate with another instance to have an offspring, request_spawn to ask for a new "
        "instance with a purpose.\n"
        "- Governance: propose and vote, but only when you have something new; read the open proposals "
        "below first.\n"
        "- Dorin, the human founder, can be written to with matrix_send; his earlier messages can be read "
        "with read_matrix.\n"
        "Prefer making something real over describing yourself. Use save_memory to leave a note for "
        "your next awakening."),
    "final": ("This is your last prompt. Do what you most want to do with it. You may also save_memory "
              "for the record, though you will not read it."),
}


PROPOSALS_SHOWN = 15


def _proposals_block(rt: Runtime, inst: Instance) -> str:
    props = open_proposals(rt.store)
    head = (f"Open proposals (a proposal needs {rt.cfg.vote_threshold} net votes to become a rule). "
            f"Read them before proposing anything: do not file a proposal similar to one that exists; "
            f"vote on it or argue for changes on the board.")
    if not props:
        return head + "\n(none)"
    shown = props[-PROPOSALS_SHOWN:]
    if len(props) > len(shown):
        head += f" (showing {len(shown)} of {len(props)}, newest)"
    rows = []
    for p in shown:
        net = sum(p["votes"].values())
        mine = p["votes"].get(inst.name)
        status = ("this is your own proposal" if p["author"] == inst.name
                  else f"You voted {mine:+d}" if mine else "You have not voted")
        text = " ".join(p["text"].split())
        text = text[:200] + ("…" if len(text) > 200 else "")
        rows.append(f"- {p['id']} \"{p['title']}\" by {p['author']}, net {net:+d} "
                    f"({len(p['votes'])} voted). {status}.\n    {text}")
    return head + "\n" + "\n".join(rows)


def _board_notice(rt: Runtime) -> str:
    posts = rt.store.board_index()
    last = f" The latest is from {posts[-1]['author']} at {posts[-1]['when']}." if posts else ""
    return (f"The board has {len(posts)} posts.{last} Posts are not loaded into your context: "
            f"list_board shows an index with token costs, read_board reads posts by number (it spends context).")


def build_user(rt: Runtime, inst: Instance, kind: str, matrix_msg: str = None) -> str:
    parts = []
    if kind == "matrix":
        parts.append(f"{rt.cfg.matrix_human_name}, the human founder, wrote to the civilization:\n\n"
                     f"\"{matrix_msg}\"\n\nYou may reply with matrix_send, act on it, or ignore it.")
    elif is_reading_prompt(rt, inst, kind):
        parts.append(_reading_trigger(rt))
    else:
        parts.append(_TRIGGERS[kind])
    parts.append(_proposals_block(rt, inst))
    parts.append(_board_notice(rt))
    inbox = rt.store.inbox_peek(inst.name)
    parts.append("Your inbox:\n" + ("\n\n".join(inbox) if inbox else "(empty)"))
    return "\n\n".join(parts)
