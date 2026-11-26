import pytest
from budget import ContextBudget, est_tokens
from heritage import Catalog


def test_est_tokens():
    assert est_tokens("") == 1 and est_tokens("a" * 400) == 101


def test_budget_floor_and_fits():
    b = ContextBudget(total=1000, reserve=200)
    assert b.remaining == 800 and b.fits(800) and not b.fits(801)
    b.spend(5000)
    assert b.remaining == 0


def test_add_and_parse_roundtrip(tmp_path):
    c = Catalog(tmp_path)
    a = c.add("Pale Rest", "On Mud", ["Mud Things", "mud-things", "water"], "About mud.\nReally.", "Body text here.")
    assert a.id == "H-001" and a.tags == ("mud-things", "water")
    got = Catalog(tmp_path).get("H-001")
    assert got.title == "On Mud" and got.summary == "About mud. Really." and got.body.strip() == "Body text here."
    assert got.cost == est_tokens(got.body)


def test_ids_increment_and_never_overwrite(tmp_path):
    c = Catalog(tmp_path)
    c.add("a", "t1", ["x"], "s", "b")
    c.add("a", "t2", ["y"], "s", "b")
    assert [a.id for a in c.articles()] == ["H-001", "H-002"]


def test_tag_counts_and_query_ranking(tmp_path):
    c = Catalog(tmp_path)
    c.add("a", "t1", ["culture", "death"], "s", "b")
    c.add("a", "t2", ["culture"], "s", "b")
    c.add("a", "t3", ["art"], "s", "b")
    assert c.tag_counts() == {"art": 1, "culture": 2, "death": 1}
    assert [a.id for a in c.query(["death", "culture"])] == ["H-001", "H-002"]
    assert c.query(["nothing"]) == []


def test_add_requires_tags_and_title(tmp_path):
    with pytest.raises(ValueError):
        Catalog(tmp_path).add("a", "t", [], "s", "b")
    with pytest.raises(ValueError):
        Catalog(tmp_path).add("a", "  ", ["x"], "s", "b")


def test_unparseable_article_file_is_skipped(tmp_path):
    c = Catalog(tmp_path)
    c.add("a", "ok", ["x"], "s", "b")
    (tmp_path / "H-009.md").write_text("no frontmatter at all")
    assert [a.id for a in c.articles()] == ["H-001"]
    assert c.tag_counts() == {"x": 1}


def test_articles_remember_the_civilization_that_wrote_them(tmp_path):
    c = Catalog(tmp_path)
    c.add("a", "old", ["x"], "s", "b")
    c.add("a", "new", ["x"], "s", "b", civ=2)
    assert [a.civ for a in c.articles()] == [None, 2]
    assert Catalog(tmp_path).get("H-002").civ == 2


def test_query_puts_the_current_civilization_first_then_newer_then_the_founding_heritage(tmp_path):
    c = Catalog(tmp_path)
    c.add("a", "seed", ["x"], "s", "b")
    c.add("a", "civ1", ["x"], "s", "b", civ=1)
    c.add("a", "civ3", ["x"], "s", "b", civ=3)
    c.add("a", "civ2", ["x"], "s", "b", civ=2)
    assert [a.title for a in c.query(["x"], current_civ=3)] == ["civ3", "civ2", "civ1", "seed"]
    assert [a.title for a in c.query(["x"])] == ["seed", "civ1", "civ3", "civ2"]  # no preference: by id
