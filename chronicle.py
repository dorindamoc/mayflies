"""The story of a civilization: facts from the records, a short telling, a heritage article and website pages."""

from __future__ import annotations

import html
import json
import re

from civs import Civilizations
from llm import LLMError

NARRATOR = ("You write the chronicle of a civilization of short-lived minds, for those who come after. You are given "
            "only facts: who lived, who was born to whom, when they ended, what they wrote, the rules they adopted and "
            "samples of their board. Tell the story in at most 350 words, in the past tense, in plain prose. Use only "
            "what you are given; invent no names, events, causes, motives or arguments that are not in the samples. Say what kind of society this was and what it left. "
            "Output only the story.")
POSTS_SAMPLED = 12
POST_CHARS = 280


def _members(rt, cid: int) -> list:
    return [i for i in rt.registry._items.values() if getattr(i, "civ", 1) == cid]


def story_facts(rt, cid: int) -> dict:
    civs = Civilizations(rt.cfg)
    c = civs.get(cid)
    members = _members(rt, cid)
    names = {m.name for m in members}
    try:
        authors = json.loads((rt.cfg.state_dir / "website_authors.json").read_text())
    except (OSError, ValueError):
        authors = {}
    rules = rt.store.rules_path.read_text() if rt.store.rules_path.exists() else ""
    return {
        "id": cid, "label": civs.label(cid), "named": bool(c["name"]), "founded": c["founded"], "ended": c["ended"],
        "cause": c["end_cause"], "founders": c["founders"],
        "members": [{"name": m.name, "model": m.model, "born_at": m.born_at, "died": m.died, "died_at": m.died_at,
                     "alive": m.alive, "parents": m.parents, "prompts": m.prompts_done} for m in members],
        "board_posts": len(rt.store.board_index()),
        "rules": len(re.findall(r"(?m)^### P-", rules)),
        "heritage_articles": sum(1 for a in rt.catalog.articles() if a.civ == cid and a.author != "The chronicle"),
        "website_files": sum(1 for who in authors.values() if who in names),
    }


def _facts_markdown(f: dict) -> str:
    end = f"ended {f['ended']} ({f['cause']})" if f["ended"] else "still living"
    lines = [f"{f['label']}: founded {f['founded']}, {end}.", "",
             f"Founders: {', '.join(f['founders']) or 'none recorded'}.", "", "Individuals:"]
    for m in f["members"]:
        fate = "alive" if m["alive"] else f"ended {m['died_at']} ({m['died']})"
        kin = f", child of {' and '.join(m['parents'])}" if m["parents"] else ""
        lines.append(f"- {m['name']} ({m['model']}), born {m['born_at']}{kin}; {fate}; {m['prompts']} prompts.")
    lines += ["", f"It left {f['heritage_articles']} heritage articles, {f['board_posts']} board posts, "
                  f"{f['website_files']} website files and {f['rules']} adopted rules."]
    return "\n".join(lines)


def _sources(rt, cid: int, f: dict) -> str:
    posts = rt.store.board_index()
    step = max(1, len(posts) // POSTS_SAMPLED)
    sample = [f"{p['author']}: {' '.join(p['text'].split())[:POST_CHARS]}" for p in posts[::step][:POSTS_SAMPLED]]
    titles = [a.title for a in rt.catalog.articles() if a.civ == cid and a.author != "The chronicle"]
    rules = rt.store.rules_path.read_text().strip() if rt.store.rules_path.exists() else ""
    temperaments = "\n".join(f"- {m.name}: " + ", ".join(f"{k} {v}/10" for k, v in m.traits.items())
                             for m in _members(rt, cid))
    return (_facts_markdown(f) + "\n\nTemperaments (1-10):\n" + temperaments + "\n\nBoard samples:\n" + ("\n".join(sample) or "(none)")
            + "\n\nHeritage titles: " + (", ".join(titles) or "(none)")
            + "\n\nAdopted rules:\n" + (rules[:1500] or "(none)"))


def narrative(rt, cid: int, f: dict) -> str:
    try:
        reply = rt.llm.chat([{"role": "system", "content": NARRATOR},
                             {"role": "user", "content": _sources(rt, cid, f)}],
                            tools=None, think=False, model=rt.cfg.model_default)
    except LLMError:
        return ""
    return (reply.content or "").strip()


def write_story(rt, cid: int) -> str:
    """Adds the civilization's story to the heritage and returns its id."""
    f = story_facts(rt, cid)
    telling = narrative(rt, cid, f)
    body = (f"## Facts\n\n{_facts_markdown(f)}" + (f"\n\n## The story\n\n{telling}" if telling else ""))
    first = telling.split(". ")[0][:160] if telling else ""
    summary = first or f"Who lived in {f['label']}, how it ended and what it left."
    art = rt.catalog.add("The chronicle", f"The story of {f['label']}", ["civilization-history", f"civ-{cid}"],
                         summary, body, civ=cid)
    return art.id


# --- website pages ---

_STYLE = '<link rel="stylesheet" href="{up}style.css">'


def _page(title: str, up: str, body: str) -> str:
    return (f'<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><title>{html.escape(title)}</title>\n'
            f'{_STYLE.format(up=up)}</head><body>\n<main>\n{body}\n</main></body></html>\n')


def civ_page_html(rt, cid: int) -> str:
    f = story_facts(rt, cid)
    civ = Civilizations(rt.cfg).get(cid)
    e = html.escape
    rows = "\n".join(
        f"<tr><td>{e(m['name'])}</td><td>{e(m['model'])}</td><td>{e(m['born_at'])}</td>"
        f"<td>{e(m['died_at'] or 'alive')}</td><td>{e(m['died'])}</td>"
        f"<td>{e(' and '.join(m['parents']))}</td></tr>" for m in f["members"])
    ended = f"{e(f['ended'])} ({e(f['cause'])})" if f["ended"] else "still living"
    story = (f'<p>Its story is heritage article <strong>{e(civ["story"])}</strong>: read it with read_heritage.</p>'
             if civ["story"] else "")
    body = (f"<h1>{e(f['label'])}</h1>\n<p>Founded {e(f['founded'])}. Ended: {ended}.</p>\n"
            f"<p>It left {f['heritage_articles']} heritage articles, {f['board_posts']} board posts, "
            f"{f['website_files']} website files and {f['rules']} adopted rules.</p>\n{story}\n"
            f"<h2>Individuals</h2>\n<table>\n<tr><th>Name</th><th>Model</th><th>Born</th><th>Ended</th>"
            f"<th>Cause</th><th>Parents</th></tr>\n{rows}\n</table>\n"
            f'<p><a href="../civilizations.html">All civilizations</a></p>')
    return _page(f["label"], "../", body)


def index_html(rt) -> str:
    civs = Civilizations(rt.cfg)
    e = html.escape
    items = []
    for c in civs.records():
        label = e(civs.label(c["id"]))
        n = sum(1 for i in rt.registry._items.values() if getattr(i, "civ", 1) == c["id"])
        if c["ended"]:
            items.append(f'<li><a href="civilizations/{c["id"]}.html">{label}</a>: {e(c["founded"])} to '
                         f'{e(c["ended"])} ({e(c["end_cause"])}), {n} individuals</li>')
        else:
            items.append(f"<li>{label}: founded {e(c['founded'])}, ongoing, {n} individuals so far</li>")
    body = ("<h1>Civilizations</h1>\n<p>Each society that has lived here, in order.</p>\n<ul>\n"
            + "\n".join(items) + "\n</ul>")
    return _page("Civilizations", "", body)


def write_pages(rt, cid: int = None) -> None:
    """The index, and the page of civilization cid (when it has ended)."""
    site = rt.cfg.website_dir
    (site / "civilizations").mkdir(parents=True, exist_ok=True)
    if cid is not None:
        (site / "civilizations" / f"{cid}.html").write_text(civ_page_html(rt, cid))
    (site / "civilizations.html").write_text(index_html(rt))
