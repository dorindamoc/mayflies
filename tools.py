"""Tool definitions and dispatch for instances. Rules and registry are not writable here."""

from __future__ import annotations

import base64
import json
import re
from datetime import datetime, timezone
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from budget import ContextBudget, est_tokens
from canvas import CanvasError, check_svg, image_tokens, png_size, render_svg
from civs import NAME_MARK, Civilizations, clean_name
from config import Config
from content import ActiveContentError, check_static
from distiller import compact_note
from heritage import Catalog
from proposals import open_proposals
from registry import Instance, Registry
from store import Store, append_entry, append_line, one_line

WEBSITE_SUFFIXES = {".html", ".css", ".md", ".txt", ".svg"}
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
    details: list = field(default_factory=list)  # the same actions with the substance of what was made or read

    def add(self, action: str, detail: str = "") -> None:
        self.actions.append(action)
        self.details.append(f"{action}\n    {detail}" if detail else action)


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
    heritage_minimum: Optional[int] = None  # set in the first (reading) prompt
    memory_refusals: int = 0  # over-limit save_memory attempts refused this prompt
    llm: object = None  # for the neutral compactor of over-long notes
    images: list = field(default_factory=list)  # base64 pictures a tool made, sent back with its result
    canvas_used: int = 0  # pictures drawn or looked at this prompt


def _spec(name, description, properties=None, required=()):
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": properties or {}, "required": list(required)}}}


_S = {"type": "string"}
_TAGS = {"type": "array", "items": _S}


def tool_specs(cfg=None) -> list:
    return [
        _spec("query_heritage", "List heritage articles carrying any of the given tags (with token cost). "
              "With no tags, list every tag and how many articles it has. Shows remaining context.",
              {"tags": _TAGS}),
        _spec("read_heritage", "Read heritage articles in full, by id (like H-001). Pass several ids in one call "
              "to read them all at once. Each costs its listed tokens from your remaining context.",
              {"ids": _TAGS, "id": _S}),
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
        _spec("propose_civilization_name",
              "Propose a name for your civilization. It is an ordinary proposal: it is adopted as a rule, and the "
              "civilization takes the name, when it reaches the vote threshold; vote on it with vote. Naming is "
              "suggested, never required; an unnamed civilization is remembered as Unnamed_<number>.",
              {"name": _S, "reason": _S}, ["name"]),
        _spec("vote", "Vote +1 or -1 on an open proposal (one vote per proposal; you cannot vote on your own proposal).",
              {"proposal_id": _S, "vote": {"type": "integer"}, "comment": _S}, ["proposal_id", "vote"]),
        _spec("agree_to_procreate",
              "Have an offspring with another living instance. Name the partner and up to a few heritage ids "
              "(picks) your child should read first. The first call is an offer; the child is born only when "
              "the partner makes the same call toward you, with their own picks. The child gets no task, only "
              "its schooling.",
              {"partner": _S, "picks": {"type": "array", "items": _S}}, ["partner"]),
        _spec("list_website", "List files in the website."),
        _spec("read_website", "Read a website file.", {"path": _S}, ["path"]),
        _spec("write_website", "Write a website file (.html .css .md .txt), e.g. art/poem.html. An existing file "
              "written by someone else is not replaced unless you set overwrite true: read it and write the "
              "combined content to add to it. The site is static: scripts, inline event handlers (onclick=), frames and "
              "redirects are refused in any file.",
              {"path": _S, "content": _S, "overwrite": {"type": "boolean"}}, ["path", "content"]),
        _spec("canvas", "Draw a picture with SVG and see it: you are shown the result, so you can look at what you "
              "made and draw again. Give the full <svg> with a viewBox, using shapes, paths, gradients and text; "
              "no <image>, scripts or links to other files. Set save_as (e.g. art/moon.svg) to keep it on the "
              "website, where others can look at it. A limited number of pictures per prompt; each costs context.",
              {"svg": _S, "save_as": _S, "overwrite": {"type": "boolean"}}, ["svg"]),
        _spec("look_website", "Look at a drawing (.svg) on the website, like art/moon.svg, as a picture. "
              "Costs context and counts toward your pictures for this prompt.", {"path": _S}, ["path"]),
        _spec("matrix_send", "Send a message to Dorin.", {"message": _S}, ["message"]),
        _spec("read_matrix", "Read Dorin's earlier messages to the civilization, oldest first (default the latest "
              "10, at most 20). They cost context like any other reading.", {"limit": {"type": "integer"}}),
        _spec("save_memory", "Save a short note to remember. You will see it at your next awakening in your short-term memory, "
              "and after that it is compacted into your long-term memory. "
              f"At most {cfg.memory_fragment_max if cfg else Config.memory_fragment_max} characters, so keep it brief.",
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


def _as_list(value) -> list:
    """A list of strings from a list, a comma-separated string, or nothing."""
    if value is None:
        return []
    if isinstance(value, str):
        if value.lstrip().startswith("["):
            try:
                return _as_list(json.loads(value))
            except ValueError:
                pass
        value = re.split(r"[,;]", value)
    elif not isinstance(value, (list, tuple)):
        value = [value]
    return [str(int(v) if isinstance(v, float) and v.is_integer() else v).strip()
            for v in value if str(v).strip()]


def _first_of(a: dict, *keys):
    """The value of the first of these argument names that is present and non-empty."""
    for k in keys:
        if a.get(k) not in (None, "", []):
            return a[k]
    raise KeyError(keys[0])


def _norm_heritage_id(raw) -> str:
    """1, "1", "h-1", "H1" -> "H-001"; anything else is returned as given."""
    if isinstance(raw, float) and raw.is_integer():
        raw = int(raw)
    s = str(raw).strip()
    m = re.fullmatch(r"(?i)h?\s*-?\s*(\d+)", s)
    return f"H-{int(m.group(1)):03d}" if m else s


_BOARD_ID_KEYS = ("ids", "id", "index", "post_number", "number", "post", "n")


def _board_numbers(a: dict) -> list:
    raw = next((a[k] for k in _BOARD_ID_KEYS if a.get(k) not in (None, "", [])), None)
    if raw is None:
        raise KeyError("ids")
    items = raw if isinstance(raw, (list, tuple)) else [raw]
    out = []
    for item in items:
        if isinstance(item, dict):
            item = item.get("value", item.get("id"))
        out.extend(_as_list(item))
    return out


def _sample(schema: dict):
    t = schema.get("type")
    if t == "integer":
        return 1
    if t == "array":
        return [_sample(schema.get("items", {}))]
    return "..."


_EXAMPLES = {
    "read_heritage": {"ids": ["H-001", "H-002"]},
    "read_board": {"ids": [1]},
    "vote": {"proposal_id": "P-2026-01-01-001", "vote": 1},
}


def _example(name: str) -> str:
    """A working example call, built from the tool's own schema unless one is written out above."""
    spec = next((s["function"] for s in tool_specs() if s["function"]["name"] == name), None)
    args = _EXAMPLES.get(name)
    if args is None and spec:
        props = spec["parameters"]["properties"]
        args = {k: _sample(props.get(k, {})) for k in spec["parameters"]["required"]}
    return f"{name}({json.dumps(args or {})})"


def _remaining(ctx) -> str:
    return f"[context remaining: {ctx.budget.remaining} tokens]"


# ---- handlers ------------------------------------------------------------

HERITAGE_LIST_MAX = 60


def _article_row(ctx, x) -> str:
    civs = Civilizations(ctx.cfg)
    where = f" [{civs.label(x.civ)}]" if civs.records() else ""
    return f"{x.id}{where} | {x.title} | {x.cost} tokens | {x.summary} | tags: {', '.join(x.tags)}"


def _query_heritage(ctx, a):
    tags = _as_list(a.get("tags"))
    if not tags:
        counts = ctx.catalog.tag_counts()
        lines = [f"{t} ({n})" for t, n in counts.items()] or ["(no articles yet)"]
        out = "Heritage tags: " + ", ".join(lines)
        arts = sorted(ctx.catalog.articles(), key=lambda a: ctx.catalog.recency(a, ctx.instance.civ))
        if arts and len(arts) <= HERITAGE_LIST_MAX:
            out += ("\nArticles (read some with read_heritage, e.g. {\"ids\": [\"H-001\", \"H-002\"]}):\n"
                    + "\n".join(_article_row(ctx, x) for x in arts))
        elif arts:
            out += "\nMany articles exist: query_heritage with some of these tags (a list) to see their ids."
        return out + "\n" + _remaining(ctx)
    arts = ctx.catalog.query(tags, current_civ=ctx.instance.civ)
    if not arts:
        return "No articles match those tags.\n" + _remaining(ctx)
    return "\n".join(_article_row(ctx, x) for x in arts) + "\n" + _remaining(ctx)


def _heritage_ids(a: dict) -> list:
    raw = a.get("ids")
    if raw in (None, "", []):
        raw = a.get("id")
    ids = [_norm_heritage_id(x) for x in _as_list(raw)]
    if not ids:
        raise KeyError("ids")
    return list(dict.fromkeys(ids))


def _read_heritage(ctx, a):
    ids = _heritage_ids(a)
    arts = []
    for hid in ids:
        art = ctx.catalog.get(hid)
        if art is None:
            return (f"Error: no article {hid!r}. Article ids look like H-001; "
                    f"list them with query_heritage (no arguments). Nothing was read.")
        arts.append(art)
    read, skipped = [], []
    for art in arts:
        if ctx.budget.fits(art.cost):
            ctx.budget.spend(art.cost)
            ctx.heritage_read += art.cost
            read.append(art)
        else:
            skipped.append(art)
    if not read:
        a0 = skipped[0]
        return (f"Not enough context: {a0.id} costs {a0.cost} tokens, "
                f"you have {ctx.budget.remaining} remaining. Nothing was read.")
    out = "\n\n".join(f"# {x.title} ({x.id}, by {x.author})\n\n{x.body}" for x in read)
    if skipped:
        out += ("\n\nNot read (did not fit in your remaining context): "
                + ", ".join(f"{x.id} ({x.cost} tokens)" for x in skipped))
    if ctx.heritage_minimum is not None:
        out += (f"\n\n[You have read {ctx.heritage_read} of the {ctx.heritage_minimum} tokens of heritage "
                f"you are meant to read in this first prompt.]")
    return out + "\n" + _remaining(ctx)


def _add_heritage(ctx, a):
    body = str(_first_of(a, "body", "text", "content")).strip()
    summary = a.get("summary") or re.split(r"(?<=[.!?])\s", body, maxsplit=1)[0][:160]
    art = ctx.catalog.add(ctx.instance.name, a["title"], _as_list(a["tags"]), summary, body, civ=ctx.instance.civ)
    return f"Added {art.id} with tags {', '.join(art.tags)}."


def _board_post(ctx, a):
    ctx.store.board_post(ctx.instance.name, _check_len(str(_first_of(a, "text", "post", "content", "message", "body")), "post"))
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
    ids = _board_numbers(a)
    if not ids or len(ids) > BOARD_READ_MAX:
        return f"Error: give between 1 and {BOARD_READ_MAX} post numbers, e.g. {_example('read_board')}."
    by_n = {p["n"]: p for p in ctx.store.board_index()}
    chosen = []
    for raw in ids:
        try:
            post = by_n.get(int(float(raw)))
        except (TypeError, ValueError):
            post = None
        if post is None:
            return f"Error: no board post {raw!r}. Post numbers come from list_board."
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


def _propose_civilization_name(ctx, a):
    try:
        name = clean_name(a["name"])
    except ValueError as e:
        return f"Error: {e}"
    title = f"Name the civilization: {name}"
    if any(p["title"].lower() == title.lower() for p in open_proposals(ctx.store)):
        return f"Error: a proposal to name the civilization {name!r} is already open. Vote on it."
    reason = one_line(str(a.get("reason") or "")) or "A name for the society we are."
    pid = ctx.store.next_id("P", ctx.store.proposals_path)
    append_entry(ctx.store.proposals_path,
                 f"### {pid} — {title}\nAuthor: {ctx.instance.name}\nMotivation: {reason}\n"
                 f"{NAME_MARK} {name}\nProposed text:\nThis civilization is named {name}.")
    return f"Proposal to name the civilization {name} filed as {pid}"


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
    append_line(ctx.store.votes_path, line)
    return f"Vote recorded on {pid}."


def _picks(raw) -> list:
    """Heritage ids as a list, from a list or a string such as "H-001, H-002"."""
    if raw is None or raw == "":
        return []
    items = raw if isinstance(raw, list) else re.split(r"[,\s]+", str(raw))
    out = []
    for item in items:
        item = str(item).strip()
        if item and item not in out:
            out.append(item)
    return out


def _agree_to_procreate(ctx, a):
    partner = str(a["partner"]).strip()
    me = ctx.instance.name
    other = ctx.registry.get(partner)
    if other is None:
        return f"Error: {partner} is unknown."
    if partner == me:
        return "Error: you cannot procreate with yourself."
    if not other.alive:
        return f"Error: {partner} is no longer alive."
    picks = _picks(a.get("picks"))
    limit = ctx.cfg.education_picks
    if len(picks) > limit:
        return f"Error: name at most {limit} heritage ids for your child's schooling."
    missing = [p for p in picks if ctx.catalog.get(p) is None]
    if missing:
        return f"Error: no such heritage: {', '.join(missing)}."
    offers = ctx.store.offers()
    theirs = next((o for o in offers if o["from"] == partner and o["to"] == me), None)
    if theirs:
        offers.remove(theirs)
        ctx.store.save_offers(offers)
        education = list(theirs["picks"]) + [p for p in picks if p not in theirs["picks"]]
        pid = ctx.store.next_id("PA", ctx.store.procreation_path)
        append_entry(ctx.store.procreation_path,
                     f"### {pid}\nParents: {partner} | {me}\nEducation: {', '.join(education)}\nWritten by: {me}")
        return f"Agreed ({pid}). Your child will be born when a slot is free."
    offers = [o for o in offers if not (o["from"] == me and o["to"] == partner)]
    offers.append({"from": me, "to": partner, "picks": picks, "age": 0})
    ctx.store.save_offers(offers)
    suggested = ", ".join(picks) or "none"
    ctx.store.inbox_append(
        partner, me,
        f"{me} offers to have an offspring with you. {me} would have the child read first: {suggested}. "
        f"To agree, call agree_to_procreate with partner \"{me}\" and your own picks "
        f"(up to {limit} heritage ids). The offer lapses if you do not answer within "
        f"{ctx.cfg.offer_expiry_rounds} rounds.")
    return f"Offered to {partner}. The child is born only if {partner} agrees too."


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


def _truthy(v) -> bool:
    return v is True or str(v).strip().lower() in ("true", "1", "yes")


def _website_authors(ctx) -> tuple:
    path = ctx.cfg.state_dir / "website_authors.json"
    try:
        return path, json.loads(path.read_text())
    except (OSError, ValueError):
        return path, {}


def _save_website(ctx, rel: str, content: str, overwrite) -> str:
    """Write a website file as this instance; returns an error text, or "" when written."""
    if len(content.encode()) > WEBSITE_MAX_BYTES:
        return "Error: file too large."
    target = _website_path(ctx.cfg, rel)
    try:
        check_static(content)
        if target.suffix == ".svg":
            check_svg(content)
    except (ActiveContentError, CanvasError) as e:
        return f"Error: {e}"
    key = str(target.relative_to(ctx.cfg.website_dir.resolve()))
    path, authors = _website_authors(ctx)
    owner = authors.get(key)
    if target.exists() and owner != ctx.instance.name and not _truthy(overwrite):
        who = f", written by {owner}" if owner else ""
        return (f"Error: {rel} already exists{who}. Writing would replace it. To add to it, read it "
                f"(read_website) and write the combined content with overwrite true; or choose another path.")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    authors[key] = ctx.instance.name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(authors))
    return ""


def _write_website(ctx, a):
    error = _save_website(ctx, str(a["path"]), str(a["content"]), a.get("overwrite"))
    return error or f"Wrote {a['path']}."


def _show(ctx, svg: str, saved: str = "") -> str:
    """Render, charge the context for the picture, and queue it to go back with the tool result."""
    if ctx.canvas_used >= ctx.cfg.canvas_max_per_prompt:
        return (f"Error: you have reached the limit of {ctx.cfg.canvas_max_per_prompt} pictures for this prompt. "
                f"Nothing was drawn.")
    try:
        png = render_svg(svg, ctx.cfg.canvas_size)
    except CanvasError as e:
        return f"Error: {e}"
    w, h = png_size(png)
    cost = image_tokens(w, h)
    if not ctx.budget.fits(cost):
        return f"Not enough context: the picture costs {cost} tokens, you have {ctx.budget.remaining} remaining. Nothing was drawn."
    ctx.budget.spend(cost)
    ctx.canvas_used += 1
    ctx.images.append(base64.b64encode(png).decode())
    return f"Rendered {w}x{h} image ({cost} tokens of context).{saved}"


def _canvas(ctx, a):
    svg, save_as = str(a["svg"]), str(a.get("save_as") or "")
    if save_as and not save_as.lower().endswith(".svg"):
        return "Error: save_as must be a .svg file, for example art/moon.svg."
    if save_as:
        try:
            check_svg(svg)
        except CanvasError as e:
            return f"Error: {e}"
        error = _save_website(ctx, save_as, svg, a.get("overwrite"))
        if error:
            return error
    return _show(ctx, svg, f" Saved to {save_as}." if save_as else "")


def _look_website(ctx, a):
    path = str(a["path"])
    target = _website_path(ctx.cfg, path)
    if target.suffix != ".svg":
        return "Error: look_website shows .svg drawings only; use read_website for other files."
    if not target.is_file():
        return f"Error: {path} does not exist."
    return _show(ctx, target.read_text())


def _matrix_send(ctx, a):
    if ctx.matrix is None:
        return "Matrix is not configured."
    ctx.matrix.send(f"[{ctx.instance.name}] {a['message']}")
    return "Sent to Dorin."


MATRIX_READ_DEFAULT = 10
MATRIX_READ_MAX = 20


def _read_matrix(ctx, a):
    if ctx.matrix is None:
        return "Matrix is not configured."
    try:
        limit = min(MATRIX_READ_MAX, max(1, int(a.get("limit") or MATRIX_READ_DEFAULT)))
    except (TypeError, ValueError):
        limit = MATRIX_READ_DEFAULT
    try:
        messages = ctx.matrix.fetch_human_messages(limit=MATRIX_READ_MAX)[-limit:]
    except Exception as e:  # network or server trouble must not break the turn
        return f"Error: could not read Matrix: {e}"
    if not messages:
        return "There are no messages from Dorin."
    rows = [f"[{datetime.fromtimestamp(m['ts'] / 1000, tz=timezone.utc):%Y-%m-%d %H:%M} UTC] {m['body']}"
            for m in messages]
    return "\n\n".join(rows)


MEMORY_REFUSALS = 2  # over-limit notes refused before the note is compacted


def _shorten(text: str, limit: int) -> str:
    """Cut at the last sentence end that keeps at least half the limit, else at the last space."""
    cut = text[:limit]
    ends = [m.end() for m in re.finditer(r"[.!?](?=\s|$)", cut)]
    if ends and ends[-1] >= limit // 2:
        return cut[:ends[-1]].strip()
    return cut.rsplit(" ", 1)[0].strip() if " " in cut else cut


def _save_memory(ctx, a):
    text = str(_first_of(a, "text", "note", "memory", "content", "fragment")).strip()
    limit = ctx.cfg.memory_fragment_max
    if len(text) <= limit:
        ctx.outcome.fragment = text
        return "Saved. You will see this at your next awakening."
    if ctx.memory_refusals < MEMORY_REFUSALS:
        ctx.memory_refusals += 1
        return (f"Error: that note is {len(text)} characters and the limit is {limit}. Nothing was saved. "
                f"Rewrite it much shorter, aim for about {int(limit * 0.8)} characters, keep only what you most "
                f"want to remember, and call save_memory again.")
    compacted = ""
    try:
        if ctx.llm is not None:
            compacted = compact_note(ctx.llm, ctx.cfg, ctx.instance, text)
    except Exception:  # any failure falls back to cutting the note
        compacted = ""
    if compacted and len(compacted) <= limit:
        ctx.outcome.fragment = compacted
        ctx.outcome.add(f"save_memory: note compacted from {len(text)} to {len(compacted)} characters")
        return (f"Saved, but your note was {len(text)} characters (limit {limit}), so a neutral summariser compacted "
                f"it to {len(compacted)}. This is exactly what was saved, and what you will see at your next "
                f"awakening:\n{compacted}")
    ctx.outcome.fragment = _shorten(text, limit)
    ctx.outcome.add(f"save_memory: note cut from {len(text)} to {len(ctx.outcome.fragment)} characters")
    return (f"Saved, but your note was {len(text)} characters (limit {limit}) and could not be compacted, so it was "
            f"cut to {len(ctx.outcome.fragment)}. This is exactly what was saved, and what you will see at your "
            f"next awakening:\n{ctx.outcome.fragment}")


def _die(ctx, a):
    ctx.outcome.die_reason = one_line(a.get("reason", "")) or "chosen"
    return "Understood. This prompt will be your last."


HANDLERS = {
    "query_heritage": _query_heritage, "read_heritage": _read_heritage, "add_heritage": _add_heritage,
    "board_post": _board_post, "list_board": _list_board, "read_board": _read_board,
    "send_message": _send_message, "propose": _propose, "vote": _vote,
    "propose_civilization_name": _propose_civilization_name,
    "agree_to_procreate": _agree_to_procreate,
    "list_website": _list_website, "read_website": _read_website, "write_website": _write_website,
    "canvas": _canvas, "look_website": _look_website,
    "matrix_send": _matrix_send, "read_matrix": _read_matrix,
    "save_memory": _save_memory, "die": _die,
}


def _unwrap(value):
    """Some models send {"type": "list", "value": [...]} where a plain value belongs."""
    if isinstance(value, dict):
        if "value" in value and set(value) <= {"type", "value", "description"}:
            return _unwrap(value["value"])
        return {k: _unwrap(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_unwrap(v) for v in value]
    return value


MADE_TOOLS = {"write_website", "canvas", "board_post", "add_heritage", "matrix_send", "send_message", "propose",
              "propose_civilization_name", "agree_to_procreate"}
READ_TOOLS = {"read_heritage", "read_board", "read_website", "read_matrix"}
MADE_CHARS = 600
READ_CHARS = 300
READ_ITEMS = 6
_ITEM_START = re.compile(r"\n\n(?=# |#\d)")


def _detail(name: str, arguments, result: str) -> str:
    """What the distiller should know about a call: the gist of what was made, or an excerpt of what was read."""
    if str(result).startswith("Error"):
        return one_line(result)[:200]
    if name in MADE_TOOLS and isinstance(arguments, dict):
        pairs = [(k, one_line(str(v))) for k, v in arguments.items() if isinstance(v, (str, list, dict)) and v]
        pairs.sort(key=lambda kv: len(kv[1]) > 80)  # short fields (path, title) first, so a cut loses prose
        return one_line("; ".join(f"{k}: {v}" for k, v in pairs))[:MADE_CHARS]
    if name in READ_TOOLS:
        items = _ITEM_START.split(str(result))[:READ_ITEMS] if name in ("read_heritage", "read_board") else [str(result)]
        return "\n    ".join(one_line(i)[:READ_CHARS] for i in items)
    return ""


def dispatch(ctx: ToolContext, name: str, arguments: dict) -> str:
    handler = HANDLERS.get(name)
    if handler is None:
        return f"Error: unknown tool {name!r}."
    arguments = _unwrap(arguments) if isinstance(arguments, dict) else arguments
    try:
        result = handler(ctx, arguments or {})
    except KeyError as e:
        result = f"Error: missing argument {e}. A working call looks like: {_example(name)}"
    except Exception as e:  # tool failures must never crash a turn
        result = f"Error: {e}"
    ctx.outcome.add(f"{name}: {one_line(json.dumps(arguments, default=str))[:120]}",
                    _detail(name, arguments, result))
    if name not in ("read_heritage", "read_board"):
        ctx.budget.spend(est_tokens(result))
    return result
