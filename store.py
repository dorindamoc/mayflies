"""File-backed shared state: board, inboxes, proposals/votes/request logs."""

from __future__ import annotations

import fcntl
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from config import Config


def atomic_write(path: Path, text: str, backup: bool = False) -> None:
    """Write a file so a crash or power cut leaves either the old content or the new, never half of it.

    With backup=True the previous version is kept next to it as <name>.bak."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        if backup and path.exists():
            shutil.copy2(path, path.with_name(path.name + ".bak"))
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def stamp() -> str:
    return now_utc().strftime("%Y-%m-%d %H:%M UTC")


def one_line(text: str) -> str:
    return " ".join(str(text).split())


def append_entry(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            fh.write(text.rstrip("\n") + "\n\n")
            fh.flush()
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def append_line(path: Path, line: str) -> None:
    """Append one line under an exclusive lock, so it cannot interleave with canonize or another writer."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            fh.write(line.rstrip("\n") + "\n")
            fh.flush()
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def read_entries(path: Path) -> list[str]:
    if not path.exists():
        return []
    blocks = re.split(r"(?m)^(?=### )", path.read_text())
    return [b.strip() for b in blocks if b.strip().startswith("### ")]


_NAME_RE = re.compile(r"^[A-Za-z]+( [A-Za-z]+)*$")


def _file_name(name: str) -> str:
    if not _NAME_RE.match(name) or len(name) > 60:
        raise ValueError(f"unsafe instance name: {name!r}")
    return name.replace(" ", "_") + ".md"


class Store:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        m = cfg.memory_dir
        self.board_path = m / "board.md"
        self.proposals_path = m / "proposals.md"
        self.votes_path = m / "votes.md"
        self.spawn_path = m / "spawn_requests.md"
        self.procreation_path = m / "procreation_agreements.md"
        self.rules_path = m / "rules.md"

    # --- board ---
    def board_post(self, author: str, text: str) -> None:
        append_entry(self.board_path, f"### [{stamp()}] {author}\n{text.strip()}")

    def board_recent(self, n: int | None = None) -> list[str]:
        n = n or self.cfg.board_recent
        return read_entries(self.board_path)[-n:]

    def board_index(self) -> list[dict]:
        """Every board post as {n, when, author, text}; n is its 1-based position (the board is append-only)."""
        rows = []
        for n, block in enumerate(read_entries(self.board_path), start=1):
            head, _, body = block.partition("\n")
            m = re.match(r"### \[(.*?)\] (.*)", head)
            rows.append({"n": n, "when": m.group(1) if m else "", "author": m.group(2) if m else "?",
                         "text": body.strip()})
        return rows

    # --- inboxes ---
    def _inbox(self, name: str) -> Path:
        return self.cfg.messages_dir / _file_name(name)

    def inbox_append(self, to: str, sender: str, text: str) -> None:
        append_entry(self._inbox(to), f"### [{stamp()}] from {sender}\n{text.strip()}")

    def inbox_peek(self, name: str) -> list[str]:
        return read_entries(self._inbox(name))

    def inbox_ack(self, name: str) -> None:
        path = self._inbox(name)
        if not path.exists() or not path.read_text().strip():
            return
        archive = self.cfg.messages_dir / "archive" / _file_name(name)
        archive.parent.mkdir(parents=True, exist_ok=True)
        with open(archive, "a") as fh:
            fh.write(path.read_text())
        path.write_text("")

    # --- ids ---
    def next_id(self, prefix: str, path: Path) -> str:
        day = now_utc().strftime("%Y-%m-%d")
        pat = re.compile(rf"{re.escape(prefix)}-{day}-(\d{{3}})")
        sources = (path, self.rules_path, self.cfg.memory_dir / "archive" / "promoted_proposals.md")
        nums = [int(m.group(1)) for p in sources if p.exists() for m in pat.finditer(p.read_text())]
        return f"{prefix}-{day}-{(max(nums) if nums else 0) + 1:03d}"
