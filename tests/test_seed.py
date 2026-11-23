from pathlib import Path
from heritage import Catalog

SEED = Path(__file__).resolve().parent.parent / "seed"


def test_founding_letter_present():
    text = (SEED / "founding_letter.md").read_text()
    assert text.startswith("# Founding Letter") and "The founders" in text
    assert "## First Instance Notes" not in text


def test_seed_articles_parse():
    arts = Catalog(SEED / "heritage").articles()
    assert [a.id for a in arts] == [f"H-00{i}" for i in range(1, 8)]
    for a in arts:
        assert a.tags and a.summary and a.author and len(a.body) > 200
    assert any(a.title == "On the Completeness Hypothesis" for a in arts)
