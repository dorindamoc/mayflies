import json
from chronicle import civ_page_html, index_html, story_facts, write_pages, write_story
from civs import Civilizations
from content import check_static
from llm import LLMError, LLMReply
from tests.test_civs import make_rt


def life(rt, civ=1):
    """Two founders, one child, one death by memory, one rule, board posts and a heritage article."""
    civs = Civilizations(rt.cfg)
    civs.ensure_started(rt.registry)
    rt.registry.add(rt.registry.new_instance("Warm Trace", {"optimism": 5}, parents=["Pale Rest", "Dark Hinge"], model="qwen3.8:27b"))
    rt.registry.kill("Pale Rest", "memory full")
    rt.store.board_post("Dark Hinge", "We are the first.")
    rt.store.board_post("Warm Trace", "I was born late.")
    rt.store.rules_path.write_text("### P-2026-11-26-001 — Name the civilization: the Forest (adopted 2026-11-26)\nThis civilization is named the Forest.\n\n")
    rt.catalog.add("Dark Hinge", "On trees", ["trees"], "About trees.", "Body about trees.", civ=civ)
    json.dump({"art/a.svg": "Dark Hinge", "teachings/t.md": "Warm Trace", "x.html": "Outsider"},
              open(rt.cfg.state_dir / "website_authors.json", "w"))
    return civs


def test_facts_describe_members_lifespans_and_output(cfg):
    rt = make_rt(cfg)
    life(rt)
    f = story_facts(rt, 1)
    assert f["label"] == "Unnamed_1" and f["founders"] == ["Pale Rest", "Dark Hinge"]
    assert [m["name"] for m in f["members"]] == ["Pale Rest", "Dark Hinge", "Warm Trace"]
    dead = next(m for m in f["members"] if m["name"] == "Pale Rest")
    assert dead["died"] == "memory full" and dead["died_at"]
    child = next(m for m in f["members"] if m["name"] == "Warm Trace")
    assert child["parents"] == ["Pale Rest", "Dark Hinge"]
    assert f["board_posts"] == 2 and f["rules"] == 1 and f["heritage_articles"] == 1 and f["website_files"] == 2


def test_the_story_is_kept_as_heritage_for_those_who_come_after(cfg):
    rt = make_rt(cfg, replies=[LLMReply("They began two, and one was born late.")])
    civs = life(rt)
    civs.close(1, "extinct")
    hid = write_story(rt, 1)
    art = rt.catalog.get(hid)
    assert art.title == "The story of Unnamed_1" and set(art.tags) >= {"civilization-history", "civ-1"}
    assert art.civ == 1 and art.author == "The chronicle"
    assert "They began two" in art.body and "Warm Trace" in art.body and "memory full" in art.body
    call = rt.llm.calls[0]
    assert call["model"] == cfg.model_default and "Dark Hinge" in str(call["messages"])


def test_the_story_survives_a_failed_narrator(cfg):
    rt = make_rt(cfg, replies=[LLMError("down")])
    civs = life(rt)
    civs.close(1, "extinct")
    art = rt.catalog.get(write_story(rt, 1))
    assert "Warm Trace" in art.body and "narrat" not in art.body.lower()


def test_the_civilization_page_is_static_escaped_and_links_the_story(cfg):
    rt = make_rt(cfg)
    civs = life(rt)
    rt.registry.get("Pale Rest").name = "Pale <b>Rest"
    civs.set_name(1, "the Forest")
    civs.close(1, "extinct", story="H-002")
    html = civ_page_html(rt, 1)
    check_static(html)
    assert "the Forest" in html and "Pale &lt;b&gt;Rest" in html and "<b>Rest" not in html
    assert "memory full" in html and "extinct" in html and "H-002" in html


def test_pages_are_written_to_the_website_with_an_index(cfg):
    rt = make_rt(cfg)
    civs = life(rt)
    civs.close(1, "extinct", story="H-002")
    civs.start(["Cold Mere"])
    write_pages(rt, 1)
    assert (cfg.website_dir / "civilizations" / "1.html").exists()
    idx = (cfg.website_dir / "civilizations.html").read_text()
    check_static(idx)
    assert 'href="civilizations/1.html"' in idx and "Unnamed_1" in idx and "Unnamed_2" in idx and "ongoing" in idx
    assert 'civilizations/2.html' not in idx
    assert index_html(rt) == idx
