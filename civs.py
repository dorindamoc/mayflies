"""Civilizations: a numbered society with a life (founded, ended), an optional name chosen by vote, and members."""

from __future__ import annotations

import json
import re
import shutil
from typing import Optional

from store import atomic_write, stamp

NAME_OK = re.compile(r"^[^\W_][\w' \-]{1,59}$")
NAME_MARK = "Names the civilization:"


def clean_name(raw: str) -> str:
    name = " ".join(str(raw).split())
    if "\n" in str(raw).strip() or not NAME_OK.match(name):
        raise ValueError("a civilization's name is 2-60 letters, digits, spaces, apostrophes or hyphens, on one line")
    return name


def adopted_name(block: str) -> Optional[str]:
    m = re.search(rf"(?m)^{re.escape(NAME_MARK)} (.+)$", block)
    return m.group(1).strip() if m else None


class Civilizations:
    def __init__(self, cfg):
        self.cfg = cfg
        self.path = cfg.state_dir / "civilizations.json"

    def records(self) -> list:
        try:
            return json.loads(self.path.read_text())
        except (OSError, ValueError):
            return []

    def _save(self, records: list) -> None:
        self.cfg.state_dir.mkdir(parents=True, exist_ok=True)
        atomic_write(self.path, json.dumps(records, indent=2))

    def get(self, cid: int) -> Optional[dict]:
        return next((c for c in self.records() if c["id"] == cid), None)

    def current(self) -> Optional[dict]:
        open_ones = [c for c in self.records() if not c["ended"]]
        return open_ones[-1] if open_ones else None

    def label(self, cid) -> str:
        c = self.get(cid) if cid is not None else None
        return (c["name"] or f"Unnamed_{c['id']}") if c else "founding heritage"

    def start(self, founders: list) -> dict:
        records = self.records()
        c = {"id": len(records) + 1, "name": "", "founded": stamp(), "ended": "", "end_cause": "",
             "founders": list(founders), "story": ""}
        self._save(records + [c])
        return c

    def _update(self, cid: int, **fields) -> None:
        records = self.records()
        for c in records:
            if c["id"] == cid:
                c.update(fields)
        self._save(records)

    def set_name(self, cid: int, name: str) -> None:
        self._update(cid, name=name)

    def close(self, cid: int, cause: str, story: str = "") -> None:
        self._update(cid, ended=stamp(), end_cause=cause, story=story)

    def set_story(self, cid: int, story: str) -> None:
        self._update(cid, story=story)

    def ensure_started(self, registry) -> None:
        """A population that predates civilizations becomes civilization 1."""
        if self.records() or not registry._items:
            return
        self.start([i.name for i in registry._items.values()])
        for inst in registry._items.values():
            inst.civ = 1
        registry.save()


def full_name(cfg, inst) -> str:
    civs = Civilizations(cfg)
    c = civs.get(getattr(inst, "civ", 1))
    return f"{inst.name} of {c['name']}" if c and c["name"] else inst.name


def apply_adopted_names(cfg, promoted_ids) -> list:
    """Rules just adopted that name the civilization: the current civilization takes the (latest) adopted name."""
    civs = Civilizations(cfg)
    cur = civs.current()
    archive = cfg.memory_dir / "archive" / "promoted_proposals.md"
    if cur is None or not promoted_ids or not archive.exists():
        return []
    text = archive.read_text()
    named = []
    for pid in promoted_ids:
        m = re.search(rf"(?m)^### {re.escape(pid)} —.*$", text)
        if not m:
            continue
        head = text[m.start(): m.start() + 1200].split("Proposed text:", 1)[0]
        name = adopted_name(head)
        if name:
            try:
                name = clean_name(name)
            except ValueError:
                continue
            civs.set_name(cur["id"], name)
            named.append((cur["id"], name))
    return named


_CIVIL_FILES = ["board.md", "proposals.md", "votes.md", "rules.md", "procreation_agreements.md"]
_CIVIL_STATE = ["offers.json", "processed.json", "round.json"]


def archive_civilization(cfg, cid: int) -> None:
    """Move a civilization's own records (board, proposals, votes, rules, agreements, offers, inboxes) into
    memory/archive/civ-<id>/ and leave empty files for the next one. Heritage, the website and the dead
    instances' memories stay where they are."""
    dest = cfg.memory_dir / "archive" / f"civ-{cid}"
    dest.mkdir(parents=True, exist_ok=True)
    for name in _CIVIL_FILES:
        path = cfg.memory_dir / name
        if path.exists():
            shutil.move(str(path), dest / name)
        path.touch()
    promoted = cfg.memory_dir / "archive" / "promoted_proposals.md"
    if promoted.exists():
        shutil.move(str(promoted), dest / "promoted_proposals.md")
    for name in _CIVIL_STATE:
        path = cfg.state_dir / name
        if path.exists():
            shutil.move(str(path), dest / name)
    if cfg.messages_dir.exists():
        (dest / "messages").mkdir(exist_ok=True)
        for item in cfg.messages_dir.iterdir():
            shutil.move(str(item), dest / "messages" / item.name)
