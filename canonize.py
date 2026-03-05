#!/usr/bin/env python3
"""
Canonization: tally votes, promote proposals that reach the threshold into
rules.md, and archive them. Called by daily.py after each heartbeat.

Proposal format (in proposals.md):
    ## P-YYYY-MM-DD-NNN
    **Title:** ...
    **Proposed by:** InstanceName
    **Date:** YYYY-MM-DD
    **Motivation:** ...
    **Proposed rule text:**
    ...

Vote format (in votes.md), one per line:
    P-YYYY-MM-DD-NNN | InstanceName | +1 | Optional comment
    P-YYYY-MM-DD-NNN | InstanceName | -1 | Optional comment

One vote per instance per proposal — enforced by instance name uniqueness.
"""

from __future__ import annotations

import fcntl
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

MEMORY_DIR = BASE_DIR / "memory"
VOTE_THRESHOLD = int(os.environ.get("VOTE_THRESHOLD", "3"))

PROPOSALS_FILE = MEMORY_DIR / "proposals.md"
VOTES_FILE = MEMORY_DIR / "votes.md"
RULES_FILE = MEMORY_DIR / "rules.md"
ARCHIVE_DIR = MEMORY_DIR / "archive"

PROPOSAL_ID_RE = re.compile(r"P-\d{4}-\d{2}-\d{2}-\d+")


def parse_proposals(text: str) -> dict[str, str]:
    """Return {proposal_id: full_block_text} from proposals.md content."""
    proposals: dict[str, str] = {}
    # Split on lines that start a new proposal header
    blocks = re.split(r"(?m)^(?=## P-)", text)
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        m = re.match(r"## (P-\d{4}-\d{2}-\d{2}-\d+)", block)
        if m:
            proposals[m.group(1)] = block
    return proposals


def parse_votes(text: str) -> dict[str, dict]:
    """Return {proposal_id: {net: int, voters: set[str]}} from votes.md content."""
    tallies: dict[str, dict] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 3:
            continue
        pid, voter, vote_str = parts[0], parts[1], parts[2]
        if not PROPOSAL_ID_RE.fullmatch(pid):
            continue
        try:
            vote = int(vote_str)
        except ValueError:
            continue
        if vote not in (1, -1):
            continue
        entry = tallies.setdefault(pid, {"net": 0, "voters": set()})
        if voter not in entry["voters"]:
            entry["voters"].add(voter)
            entry["net"] += vote
    return tallies


def run_canonize() -> list[str]:
    """Run canonization. Returns list of promoted proposal IDs."""
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    # Acquire exclusive lock on proposals file (create if absent)
    PROPOSALS_FILE.touch(exist_ok=True)
    VOTES_FILE.touch(exist_ok=True)

    with open(PROPOSALS_FILE, "r+") as proposals_fh:
        fcntl.flock(proposals_fh, fcntl.LOCK_EX)

        proposals_text = proposals_fh.read()
        votes_text = VOTES_FILE.read_text() if VOTES_FILE.exists() else ""

        proposals = parse_proposals(proposals_text)
        tallies = parse_votes(votes_text)

        promoted: list[str] = []
        for pid, tally in tallies.items():
            if pid in proposals and tally["net"] >= VOTE_THRESHOLD:
                promoted.append(pid)

        if not promoted:
            print(
                f"[canonize] no proposals ready "
                f"(threshold: {VOTE_THRESHOLD}, active: {len(proposals)}, "
                f"voted: {len(tallies)})"
            )
            return []

        now = datetime.now(tz=timezone.utc)
        rules_text = RULES_FILE.read_text() if RULES_FILE.exists() else ""

        remaining_blocks: list[str] = []
        for pid, block in proposals.items():
            if pid in promoted:
                # Append to rules.md
                stamp = now.strftime("%Y-%m-%d")
                rules_text += f"\n---\n\n## {pid} (canonized {stamp})\n\n{block}\n"
                # Archive
                archive_path = ARCHIVE_DIR / f"{pid}.md"
                archive_path.write_text(block)
                net = tallies[pid]["net"]
                print(f"[canonize] promoted {pid} (net votes: {net})")
            else:
                remaining_blocks.append(block)

        RULES_FILE.write_text(rules_text)

        new_proposals = "\n\n".join(remaining_blocks)
        proposals_fh.seek(0)
        proposals_fh.write(new_proposals)
        proposals_fh.truncate()

    print(f"[canonize] done — {len(promoted)} proposal(s) promoted")
    return promoted


if __name__ == "__main__":
    run_canonize()
