"""One page that links every page and drawing on the website, rebuilt by the scheduler.

Instances add pages faster than they update index pages, so some work ends up unlinked. This page is
built from the files themselves, so nothing an instance saves can be missing from it."""

from __future__ import annotations

import html
import re
from pathlib import Path

EVERYTHING = "everything.html"
SUFFIXES = {".html", ".svg"}
HOME_LINK = f'<a href="{EVERYTHING}">Everything →</a>'
TITLE = re.compile(r"(?is)<title[^>]*>(.*?)</title>")
HEADING = re.compile(r"(?is)<h1[^>]*>(.*?)</h1>")
TAGS = re.compile(r"(?s)<[^>]*>")


def site_files(site: Path) -> list:
    """Pages and drawings, as site-relative paths, without hidden folders and without this page itself."""
    found = []
    for p in sorted(site.rglob("*")):
        rel = p.relative_to(site)
        if p.is_file() and p.suffix in SUFFIXES and not any(part.startswith(".") for part in rel.parts) \
                and rel.as_posix() != EVERYTHING:
            found.append(rel.as_posix())
    return found


def _title(site: Path, rel: str) -> str:
    name = Path(rel).stem
    if rel.endswith(".svg"):
        return name
    try:
        text = (site / rel).read_text(errors="replace")
    except OSError:
        return name
    for pattern in (TITLE, HEADING):
        m = pattern.search(text)
        found = " ".join(html.unescape(TAGS.sub("", m.group(1))).split()) if m else ""
        if found:
            return found[:120]
    return name


def _section(rel: str) -> str:
    return rel.split("/", 1)[0] if "/" in rel else ""


def sitemap_html(site: Path) -> str:
    groups = {}
    for rel in site_files(site):
        groups.setdefault(_section(rel), []).append(rel)
    parts = ["<h1>Everything</h1>",
             "<p>Every page and drawing on this site, found from the files themselves. "
             "Nothing here depends on someone remembering to add a link.</p>"]
    for section in sorted(groups, key=lambda s: (s != "", s)):
        parts.append(f"<h2>{html.escape(section or 'The site')}</h2>")
        pages = [r for r in groups[section] if r.endswith(".html")]
        images = [r for r in groups[section] if r.endswith(".svg")]
        if pages:
            parts.append("<ul>\n" + "\n".join(
                f'<li><a href="{html.escape(r, quote=True)}">{html.escape(_title(site, r))}</a></li>' for r in pages)
                + "\n</ul>")
        if images:
            parts.append("<ul>\n" + "\n".join(
                f'<li><a href="{html.escape(r, quote=True)}"><img src="{html.escape(r, quote=True)}" '
                f'alt="{html.escape(_title(site, r), quote=True)}" width="120" loading="lazy"><br>'
                f'{html.escape(_title(site, r))}</a></li>' for r in images) + "\n</ul>")
    body = "\n".join(parts)
    return ('<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><title>Everything</title>\n'
            '<link rel="stylesheet" href="style.css"></head><body>\n<main>\n' + body
            + '\n<nav><a href="index.html">← Home</a></nav>\n</main></body></html>\n')


def link_from_home(site: Path) -> bool:
    """Makes sure the home page links the everything page; True when it had to add the link."""
    home = site / "index.html"
    try:
        text = home.read_text()
    except OSError:
        return False
    if EVERYTHING in text:
        return False
    if "</nav>" in text:
        new = text.replace("</nav>", f" ·\n      {HOME_LINK}\n    </nav>", 1)
    elif "</main>" in text:
        new = text.replace("</main>", f"  <p>{HOME_LINK}</p>\n  </main>", 1)
    elif "</body>" in text:
        new = text.replace("</body>", f"<p>{HOME_LINK}</p>\n</body>", 1)
    else:
        return False
    home.write_text(new)
    return True


def write_sitemap(site: Path) -> None:
    page = sitemap_html(site)
    target = site / EVERYTHING
    if not target.exists() or target.read_text() != page:
        target.write_text(page)
    link_from_home(site)
