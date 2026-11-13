"""Parsing of proposals.md and votes.md (shared by tools, prompts and canonization)."""

from __future__ import annotations

import re

from store import Store, read_entries

HEADER = re.compile(r"^### (P-\d{4}-\d{2}-\d{2}-\d{3}) — (.*)$", re.M)
VOTE = re.compile(r"^- (P-\d{4}-\d{2}-\d{2}-\d{3}) \| ([+-]1) \| (.+?) \|", re.M)


def parse_votes(votes_text: str) -> dict:
    """{proposal_id: {voter: +1|-1}}; only a voter's first vote on a proposal counts."""
    out: dict = {}
    for pid, v, voter in VOTE.findall(votes_text):
        out.setdefault(pid, {}).setdefault(voter, int(v))
    return out


def proposed_text(block: str) -> str:
    return block.split("Proposed text:", 1)[1].strip() if "Proposed text:" in block else ""


def open_proposals(store: Store) -> list:
    """Open proposals in filing order: dicts with id, title, author, text, votes ({voter: +-1})."""
    votes = parse_votes(store.votes_path.read_text() if store.votes_path.exists() else "")
    out = []
    for block in read_entries(store.proposals_path):
        m = HEADER.match(block)
        if not m:
            continue
        author = re.search(r"(?m)^Author: (.*)$", block)
        out.append({"id": m.group(1), "title": m.group(2), "author": author.group(1).strip() if author else "",
                    "text": proposed_text(block), "votes": votes.get(m.group(1), {})})
    return out
