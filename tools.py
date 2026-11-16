"""Tool definitions and dispatch for instances. Rules and registry are not writable here."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from budget import ContextBudget, est_tokens
from heritage import Catalog
from proposals import open_proposals
from registry import Instance, Registry
from store import Store, append_entry, one_line

WEBSITE_SUFFIXES = {".html", ".css", ".md", ".txt"}
WEBSITE_MAX_BYTES = 200_000
MAX_TEXT_CHARS = 4000


def _check_len(text: str, what: str) -> str:
    text = str(text)
    if len(text) > MAX_TEXT_CHARS:
        raise ValueError(f"{what} too long ({len(text)} chars, max {MAX_TEXT_CHARS}). Shorten it or add a heritage article.")
    return text


@dataclass
class TurnOutcome:
    fragment: Optional[str] = None
    die_reason: Optional[str] = None
    actions: list = field(default_factory=list)


@dataclass
class ToolContext:
    cfg: object
    instance: Instance
    registry: Registry
    store: Store
    catalog: Catalog
    budget: ContextBudget
    matrix: object
    outcome: TurnOutcome
    heritage_read: int = 0  # tokens of heritage read this turn


def _spec(name, description, properties=None, required=()):
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": properties or {}, "required": list(required)}}}


_S = {"type": "string"}
_TAGS = {"type": "array", "items": _S}


def tool_specs() -> list:
    return [
        _spec("query_heritage", "List heritage articles carrying any of the given tags (with token cost). "
              "With no tags, list every tag and how many articles it has. Shows remaining context.",
              {"tags": _TAGS}),
        _spec("read_heritage", "Read one heritage article in full. It costs its listed tokens from your remaining context.",
              {"id": _S}, ["id"]),
        _spec("add_heritage", "Add a new heritage article (permanent, append-only). Give 1-6 tags and a one-line summary.",
              {"title": _S, "tags": _TAGS, "summary": _S, "body": _S}, ["title", "tags", "summary", "body"]),
        _spec("board_post", "Post to the public board all instances can read.", {"text": _S}, ["text"]),
        _spec("list_board", "List board posts (newest last) as an index: number, author, time, token cost, a short "
              "preview. Optional author filter and limit (default 20 newest). Shows remaining context.",
              {"author": _S, "limit": {"type": "integer"}}),
        _spec("read_board", "Read board posts by number (from list_board). Each costs its listed tokens from "
              "your remaining context.", {"ids": {"type": "array", "items": {"type": "integer"}}}, ["ids"]),
        _spec("send_message", "Send a direct message to another living instance's inbox.",
              {"to": _S, "text": _S}, ["to", "text"]),
        _spec("propose", "Propose a rule. It becomes binding if it reaches the vote threshold. Before proposing, "
              "read the open proposals and the adopted rules in your prompt: do not file a proposal similar to an "
              "existing one. Vote on it, or argue for a change on the board, instead.",
              {"title": _S, "motivation": _S, "text": _S}, ["title", "motivation", "text"]),
        _spec("vote", "Vote +1 or -1 on an open proposal (one vote per proposal; you cannot vote on your own proposal).",
              {"proposal_id": _S, "vote": {"type": "integer"}, "comment": _S}, ["proposal_id", "vote"]),
        _spec("request_spawn", "Request a new instance with a stated purpose (created when a slot is free).",
              {"purpose": _S, "context": _S}, ["purpose"]),
        _spec("agree_to_procreate", "Record a confirmed agreement with another instance to have an offspring.",
              {"partner": _S}, ["partner"]),
        _spec("list_website", "List files in the website."),
        _spec("read_website", "Read a website file.", {"path": _S}, ["path"]),
        _spec("write_website", "Write a website file (.html .css .md .txt), e.g. art/poem.html.",
              {"path": _S, "content": _S}, ["path", "content"]),
        _spec("matrix_send", "Send a message to Dorin.", {"message": _S}, ["message"]),
        _spec("save_memory", "Save a short note that you will see at your next awakening (replaces your previous note).",
              {"text": _S}, ["text"]),
        _spec("die", "End your life after this prompt, freeing your slot. Optional reason.", {"reason": _S}),
    ]


def _website_path(cfg, rel: str) -> Path:
    root = cfg.website_dir.resolve()
    target = (root / rel).resolve()
    if root not in target.parents:
        raise ValueError("path escapes the website directory")
    if target.suffix not in WEBSITE_SUFFIXES:
        raise ValueError(f"only {sorted(WEBSITE_SUFFIXES)} files are allowed")
    return target


def _remaining(ctx) -> str:
    return f"[context remaining: {ctx.budget.remaining} tokens]"


# ---- handlers ------------------------------------------------------------

def _query_heritage(ctx, a):
    tags = a.get("tags") or []
    if not tags:
        counts = ctx.catalog.tag_counts()
        lines = [f"{t} ({n})" for t, n in counts.items()] or ["(no articles yet)"]
        return "Heritage tags: " + ", ".join(lines) + "\n" + _remaining(ctx)
    arts = ctx.catalog.query(tags)
    if not arts:
        return "No articles match those tags.\n" + _remaining(ctx)
    rows = [f"{x.id} | {x.title} | {x.cost} tokens | {x.summary} | tags: {', '.join(x.tags)}" for x in arts]
    return "\n".join(rows) + "\n" + _remaining(ctx)


def _read_heritage(ctx, a):
    art = ctx.catalog.get(str(a["id"]))
    if art is None:
        return f"Error: no article {a['id']}"
    if not ctx.budget.fits(art.cost):
        return (f"Not enough context: {art.id} costs {art.cost} tokens, "
                f"you have {ctx.budget.remaining} remaining. Nothing was read.")
    ctx.budget.spend(art.cost)
    ctx.heritage_read += art.cost
    return f"# {art.title} ({art.id}, by {art.author})\n\n{art.body}\n\n{_remaining(ctx)}"


def _add_heritage(ctx, a):
    art = ctx.catalog.add(ctx.instance.name, a["title"], a["tags"], a["summary"], a["body"])
    return f"Added {art.id} with tags {', '.join(art.tags)}."


def _board_post(ctx, a):
    ctx.store.board_post(ctx.instance.name, _check_len(a["text"], "post"))
    return "Posted to the board."


BOARD_LIST_DEFAULT = 20
BOARD_READ_MAX = 10


def _board_cost(post) -> int:
    return est_tokens(post["text"])


def _list_board(ctx, a):
    posts = ctx.store.board_index()
    if a.get("author"):
        posts = [p for p in posts if p["author"] == str(a["author"])]
    try:
        limit = int(a.get("limit") or BOARD_LIST_DEFAULT)
    except (TypeError, ValueError):
        limit = BOARD_LIST_DEFAULT
    posts = posts[-max(1, limit):]
    if not posts:
        return "No board posts.\n" + _remaining(ctx)
    rows = [f"{p['n']} | {p['author']} | {p['when']} | {_board_cost(p)} tokens | {one_line(p['text'])[:80]}"
            for p in posts]
    return "\n".join(rows) + "\n" + _remaining(ctx)


def _read_board(ctx, a):
    ids = a["ids"]
    ids = [ids] if not isinstance(ids, (list, tuple)) else list(ids)
    if not ids or len(ids) > BOARD_READ_MAX:
        return f"Error: give between 1 and {BOARD_READ_MAX} post numbers."
    by_n = {p["n"]: p for p in ctx.store.board_index()}
    chosen = []
    for raw in ids:
        try:
            post = by_n.get(int(raw))
        except (TypeError, ValueError):
            post = None
        if post is None:
            return f"Error: no board post {raw!r}."
        chosen.append(post)
    cost = sum(_board_cost(p) for p in chosen)
    if not ctx.budget.fits(cost):
        return (f"Not enough context: these posts cost {cost} tokens, "
                f"you have {ctx.budget.remaining} remaining. Nothing was read.")
    ctx.budget.spend(cost)
    body = "\n\n".join(f"#{p['n']} [{p['when']}] {p['author']}\n{p['text']}" for p in chosen)
    return body + "\n" + _remaining(ctx)


def _send_message(ctx, a):
    to = str(a["to"])
    target = ctx.registry.get(to)
    if target is None or not target.alive:
        return f"Error: {to} is not alive."
    if to == ctx.instance.name:
        return "Error: you cannot message yourself."
    ctx.store.inbox_append(to, ctx.instance.name, _check_len(a["text"], "message"))
    return f"Sent to {to}."


def _propose(ctx, a):
    pid = ctx.store.next_id("P", ctx.store.proposals_path)
    append_entry(ctx.store.proposals_path,
                 f"### {pid} — {one_line(a['title'])}\nAuthor: {ctx.instance.name}\n"
                 f"Motivation: {one_line(a['motivation'])}\nProposed text:\n{str(a['text']).strip()}")
    return f"Proposal filed as {pid}"


def _vote(ctx, a):
    pid, v = str(a["proposal_id"]), a["vote"]
    try:
        f = float(str(v).strip().lstrip("+"))
    except ValueError:
        f = 0.0
    if isinstance(v, bool) or f not in (1.0, -1.0):
        return "Error: vote must be +1 or -1."
    v = int(f)
    prop = next((p for p in open_proposals(ctx.store) if p["id"] == pid), None)
    if prop is None:
        return f"Error: {pid} is not an open proposal."
    if prop["author"] == ctx.instance.name:
        return "Error: you cannot vote on your own proposal."
    if ctx.instance.name in prop["votes"]:
        return f"Error: you already voted on {pid}."
    comment = one_line(str(a.get("comment", ""))).replace("|", "/")
    line = f"- {pid} | {'+1' if v == 1 else '-1'} | {ctx.instance.name} | {comment}"
    with open(ctx.store.votes_path, "a") as fh:
        fh.write(line + "\n")
    return f"Vote recorded on {pid}."


def _request_spawn(ctx, a):
    sid = ctx.store.next_id("SR", ctx.store.spawn_path)
    append_entry(ctx.store.spawn_path,
                 f"### {sid} — by {ctx.instance.name}\nPurpose: {one_line(a['purpose'])}\n"
                 f"Context: {one_line(a.get('context', ''))}")
    return f"Requested {sid}. It will be created when a slot is free."


def _agree_to_procreate(ctx, a):
    partner = str(a["partner"])
    other = ctx.registry.get(partner)
    if other is None:
        return f"Error: {partner} is unknown."
    if partner == ctx.instance.name:
        return "Error: you cannot procreate with yourself."
    pid = ctx.store.next_id("PA", ctx.store.procreation_path)
    append_entry(ctx.store.procreation_path,
                 f"### {pid}\nParents: {ctx.instance.name} | {partner}\nWritten by: {ctx.instance.name}")
    return f"Recorded {pid}. An offspring will be born when a slot is free."


def _list_website(ctx, a):
    root = ctx.cfg.website_dir
    files = sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())
    return "\n".join(files) or "(empty)"


def _read_website(ctx, a):
    content = _website_path(ctx.cfg, str(a["path"])).read_text()
    cost = est_tokens(content)
    if not ctx.budget.fits(cost):
        return (f"Not enough context: {a['path']} costs {cost} tokens, "
                f"you have {ctx.budget.remaining} remaining. Nothing was read.")
    return content


def _write_website(ctx, a):
    content = str(a["content"])
    if len(content.encode()) > WEBSITE_MAX_BYTES:
        return "Error: file too large."
    target = _website_path(ctx.cfg, str(a["path"]))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return f"Wrote {a['path']}."


def _matrix_send(ctx, a):
    if ctx.matrix is None:
        return "Matrix is not configured."
    ctx.matrix.send(f"[{ctx.instance.name}] {a['message']}")
    return "Sent to Dorin."


def _save_memory(ctx, a):
    text = str(a["text"]).strip()
    if len(text) > ctx.cfg.memory_fragment_max:
        return (f"Error: memory too long ({len(text)} chars, max {ctx.cfg.memory_fragment_max}). "
                f"Shorten it and call save_memory again.")
    ctx.outcome.fragment = text
    return "Saved. You will see this at your next awakening."


def _die(ctx, a):
    ctx.outcome.die_reason = one_line(a.get("reason", "")) or "chosen"
    return "Understood. This prompt will be your last."


HANDLERS = {
    "query_heritage": _query_heritage, "read_heritage": _read_heritage, "add_heritage": _add_heritage,
    "board_post": _board_post, "list_board": _list_board, "read_board": _read_board,
    "send_message": _send_message, "propose": _propose, "vote": _vote,
    "request_spawn": _request_spawn, "agree_to_procreate": _agree_to_procreate,
    "list_website": _list_website, "read_website": _read_website, "write_website": _write_website,
    "matrix_send": _matrix_send,
    "save_memory": _save_memory, "die": _die,
}


def dispatch(ctx: ToolContext, name: str, arguments: dict) -> str:
    handler = HANDLERS.get(name)
    if handler is None:
        return f"Error: unknown tool {name!r}."
    try:
        result = handler(ctx, arguments or {})
    except KeyError as e:
        result = f"Error: missing argument {e}."
    except Exception as e:  # tool failures must never crash a turn
        result = f"Error: {e}"
    ctx.outcome.actions.append(f"{name}: {one_line(json.dumps(arguments, default=str))[:120]}")
    if name not in ("read_heritage", "read_board"):
        ctx.budget.spend(est_tokens(result))
    return result
