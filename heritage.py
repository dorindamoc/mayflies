"""Heritage catalog: articles on disk, found by tag, priced in tokens."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from budget import est_tokens
from store import stamp


@dataclass(frozen=True)
class Article:
    id: str
    title: str
    tags: tuple
    summary: str
    author: str
    date: str
    body: str
    civ: Optional[int] = None  # the civilization that wrote it; None for the founding heritage

    @property
    def cost(self) -> int:
        return est_tokens(self.body)


def _tag(raw: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", raw.strip().lower()).strip("-")


def _parse(path: Path) -> Article:
    text = path.read_text()
    _, header, body = text.split("---\n", 2)
    meta = {}
    for line in header.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    tags = tuple(t for t in (x.strip() for x in meta.get("tags", "").split(",")) if t)
    civ = meta.get("civ", "")
    return Article(meta["id"], meta.get("title", ""), tags, meta.get("summary", ""),
                   meta.get("author", ""), meta.get("date", ""), body.lstrip("\n"),
                   int(civ) if civ.isdigit() else None)


class Catalog:
    def __init__(self, directory: Path):
        self.dir = Path(directory)

    def articles(self) -> list:
        if not self.dir.exists():
            return []
        out = []
        for p in sorted(self.dir.glob("H-*.md")):
            try:
                out.append(_parse(p))
            except Exception:  # a hand-edited or damaged file must not break every prompt
                continue
        return out

    def get(self, article_id: str) -> Optional[Article]:
        for a in self.articles():
            if a.id == article_id:
                return a
        return None

    def tag_counts(self) -> dict:
        counts: dict = {}
        for a in self.articles():
            for t in a.tags:
                counts[t] = counts.get(t, 0) + 1
        return dict(sorted(counts.items()))

    @staticmethod
    def recency(a: Article, current_civ) -> tuple:
        """Sort key: the current civilization first, then newer civilizations, the founding heritage last."""
        if current_civ is None:
            return (0, a.id)
        return (0 if a.civ == current_civ else 2 if a.civ is None else 1, -(a.civ or 0), a.id)

    def query(self, tags, current_civ=None) -> list:
        wanted = {_tag(t) for t in tags}
        scored = []
        for a in self.articles():
            hits = len(wanted & set(a.tags))
            if hits:
                scored.append((-hits, self.recency(a, current_civ), a))
        return [a for _, _, a in sorted(scored, key=lambda s: (s[0], s[1]))]

    def add(self, author: str, title: str, tags, summary: str, body: str, civ: Optional[int] = None) -> Article:
        title = " ".join(title.split())
        clean = []
        for t in tags:
            t = _tag(t)
            if t and t not in clean:
                clean.append(t)
        clean = clean[:6]
        if not title or not clean:
            raise ValueError("a heritage article needs a title and at least one tag")
        self.dir.mkdir(parents=True, exist_ok=True)
        nums = [int(p.stem.split("-")[1]) for p in self.dir.glob("H-*.md")]
        art_id = f"H-{(max(nums) if nums else 0) + 1:03d}"
        summary = " ".join(summary.split())
        text = (f"---\nid: {art_id}\ntitle: {title}\ntags: {', '.join(clean)}\n"
                f"summary: {summary}\nauthor: {' '.join(author.split())}\ndate: {stamp()[:10]}\n"
                f"{f'civ: {civ}' + chr(10) if civ else ''}---\n"
                f"{body.strip()}\n")
        with open(self.dir / f"{art_id}.md", "x") as fh:
            fh.write(text)
        return _parse(self.dir / f"{art_id}.md")
