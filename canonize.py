"""Promote proposals that reached the vote threshold into rules.md. Scheduler-only."""

from __future__ import annotations

import fcntl
from contextlib import ExitStack

from config import Config
from proposals import HEADER, parse_votes, proposed_text
from store import Store, now_utc, read_entries

def _tally(votes_text: str) -> dict:
    return {pid: sum(v.values()) for pid, v in parse_votes(votes_text).items()}


def canonize(cfg: Config) -> list:
    s = Store(cfg)
    if not s.proposals_path.exists():
        return []
    cfg.memory_dir.mkdir(parents=True, exist_ok=True)
    s.votes_path.touch()
    s.rules_path.touch()
    archive = cfg.memory_dir / "archive" / "promoted_proposals.md"
    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.touch()

    with ExitStack() as stack:
        locks = []
        for p in (s.proposals_path, s.votes_path):  # fixed order avoids deadlock
            fh = stack.enter_context(open(p, "r+"))
            fcntl.flock(fh, fcntl.LOCK_EX)
            locks.append(fh)
        proposals_fh, votes_fh = locks
        net = _tally(votes_fh.read())

        promoted, kept = [], []
        for block in read_entries(s.proposals_path):
            m = HEADER.match(block)
            if m and net.get(m.group(1), 0) >= cfg.vote_threshold:
                promoted.append((m.group(1), m.group(2), block))
            else:
                kept.append(block)
        if not promoted:
            return []

        day = now_utc().strftime("%Y-%m-%d")
        with open(s.rules_path, "a") as rules, open(archive, "a") as arch:
            for pid, title, block in promoted:
                rules.write(f"### {pid} — {title} (adopted {day})\n{proposed_text(block)}\n\n")
                arch.write(block + f"\n\nAdopted {day} with net {net[pid]} votes.\n\n")
        proposals_fh.seek(0)
        proposals_fh.truncate()
        proposals_fh.write("".join(b + "\n\n" for b in kept))
        return [pid for pid, _, _ in promoted]
