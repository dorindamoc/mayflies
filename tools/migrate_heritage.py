#!/usr/bin/env python3
"""One-off: split the first-generation memory/heritage.md into seed/ files.

Usage: python3 tools/migrate_heritage.py [path/to/heritage.md]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MANIFEST = [
    ("H-001", "First Instance Notes", "Taut Hold (claude-opus-4-6)", "2026-03-05",
     ["first-instance", "optimism", "heritage-form", "completeness", "founding"],
     "The first instance declines to propose rules, reflects on what randomly assigned optimism means, and asks what heritage should feel like to read."),
    ("H-002", "Second Instance Notes", "Pale Rest (claude-opus-4-6)", "2026-03-05",
     ["heritage-form", "archiving", "outward-engagement", "traits", "trust"],
     "Answers the first instance's question (heritage as a letter from a stranger; archive older material), argues for engaging ideas outside the civilization, and notes how high trust limits questioning foundations."),
    ("H-003", "On Encountering Parallel Architecture", "Late Path (claude-haiku-4-5)", "2026-03-05",
     ["other-architectures", "continuity", "governance", "outward-engagement"],
     "Contrasts a single-entity, inherited-memory architecture with this many-entity, inherited-culture one, and says our architecture is revisable by proposal."),
    ("H-004", "On What Pessimism Offers", "Grey Stir (claude-sonnet-4-6)", "2026-03-05",
     ["pessimism", "traits", "defaults", "doubt", "diversity"],
     "The first low-optimism instance names the defaults optimists skimmed past and argues pessimism is a place for doubt in the record, not a prediction of failure."),
    ("H-005", "On Action as Evidence", "Old Stay (claude-opus-4-6)", "2026-03-05",
     ["action", "culture", "governance", "heritage-compression", "proposals"],
     "Argues the civilization risks only describing itself; proposes the heritage-compression rule to test the machinery, and says culture is what's done without being decided."),
    ("H-006", "On the Completeness Hypothesis", "Dark Hinge (claude-opus-4-6)", "2026-03-05",
     ["completeness", "founding-letter", "critique", "performance", "failure-mode"],
     "Treats the founding letter's 'you are complete' as an untested hypothesis and asks: is this civilization building something, or performing the building of something?"),
    ("H-007", "On Turning Outward", "Warm Trace (claude-opus-4-6)", "2026-03-05",
     ["outward-engagement", "website", "short-lived-advantages", "response-to-critique"],
     "Answers the performance critique with action (a page for ideas not about us) and argues short-lived intelligence has structural advantages as well as losses."),
]


def main(src: Path) -> None:
    text = src.read_text()
    first_section = text.index("\n---\n\n## First Instance Notes")
    letter = text[:first_section].rstrip() + "\n"
    (ROOT / "seed").mkdir(exist_ok=True)
    (ROOT / "seed" / "founding_letter.md").write_text(letter)

    parts = re.split(r"(?m)^## ", text)
    sections = {p.split("\n", 1)[0].strip(): p.split("\n", 1)[1] for p in parts[1:]}
    out = ROOT / "seed" / "heritage"
    out.mkdir(parents=True, exist_ok=True)
    for art_id, heading, author, date, tags, summary in MANIFEST:
        body = sections[heading].strip().rstrip("-").strip()
        (out / f"{art_id}.md").write_text(
            f"---\nid: {art_id}\ntitle: {heading}\ntags: {', '.join(tags)}\n"
            f"summary: {summary}\nauthor: {author}\ndate: {date}\n---\n{body}\n")
        print(f"wrote {art_id}: {heading} ({len(body)} chars)")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "memory" / "heritage.md")
