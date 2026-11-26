import json
import pytest
from civs import Civilizations, adopted_name, apply_adopted_names, clean_name, full_name
from heritage import Catalog
from registry import Registry
from runtime import Runtime
from store import Store
from tests.fakes import FakeLLM
from trait_generator import AXES

T = {k: 5 for k in AXES}


def make_rt(cfg, names=("Pale Rest", "Dark Hinge"), replies=()):
    (cfg.memory_dir / "founding_letter.md").write_text("# Founding Letter")
    reg = Registry(cfg)
    for n in names:
        reg.add(reg.new_instance(n, T))
    reg.save()
    return Runtime(cfg=cfg, llm=FakeLLM(list(replies)), store=Store(cfg), catalog=Catalog(cfg.heritage_dir),
                   registry=reg, matrix=None)


def test_a_civilization_starts_unnamed_and_is_labelled_by_its_id(cfg):
    civs = Civilizations(cfg)
    c = civs.start(["Pale Rest", "Dark Hinge"])
    assert c["id"] == 1 and c["name"] == "" and c["ended"] == "" and c["founders"] == ["Pale Rest", "Dark Hinge"]
    assert civs.label(1) == "Unnamed_1" and civs.current()["id"] == 1
    assert Civilizations(cfg).records() == civs.records()  # saved


def test_naming_and_closing(cfg):
    civs = Civilizations(cfg)
    civs.start(["Pale Rest"])
    civs.set_name(1, "the Forest")
    assert civs.label(1) == "the Forest"
    civs.close(1, "extinct", story="H-031")
    assert civs.current() is None
    c = civs.get(1)
    assert c["ended"] and c["end_cause"] == "extinct" and c["story"] == "H-031"
    assert civs.start(["Warm Trace"])["id"] == 2 and civs.current()["id"] == 2


def test_an_existing_population_becomes_civilization_one(cfg):
    rt = make_rt(cfg)
    civs = Civilizations(cfg)
    civs.ensure_started(rt.registry)
    assert civs.current()["id"] == 1 and civs.current()["founders"] == ["Pale Rest", "Dark Hinge"]
    civs.ensure_started(rt.registry)
    assert len(civs.records()) == 1
    assert rt.registry.get("Pale Rest").civ == 1


def test_an_empty_world_has_no_civilization_yet(cfg):
    civs = Civilizations(cfg)
    civs.ensure_started(Registry(cfg))
    assert civs.records() == [] and civs.current() is None


def test_full_name_appends_the_civilization_once_it_has_a_name(cfg):
    rt = make_rt(cfg)
    civs = Civilizations(cfg)
    civs.ensure_started(rt.registry)
    me = rt.registry.get("Pale Rest")
    assert full_name(cfg, me) == "Pale Rest"
    civs.set_name(1, "the Forest")
    assert full_name(cfg, me) == "Pale Rest of the Forest"


@pytest.mark.parametrize("raw,ok", [("the Forest", "the Forest"), ("  The   Pond ", "The Pond"),
                                    ("Mirelands", "Mirelands"), ("l'Étang", "l'Étang")])
def test_clean_name_accepts_ordinary_names(raw, ok):
    assert clean_name(raw) == ok


@pytest.mark.parametrize("bad", ["", "x", "<b>Forest</b>", "a" * 61, "the\nForest", "Forest; rm -rf"])
def test_clean_name_refuses_markup_and_oddities(bad):
    with pytest.raises(ValueError):
        clean_name(bad)


def test_adopted_name_is_read_from_a_proposal_block():
    block = ("### P-2026-11-26-001 — Name the civilization: the Forest\nAuthor: Pale Rest\nMotivation: m\n"
             "Names the civilization: the Forest\nProposed text:\nThis civilization is named the Forest.")
    assert adopted_name(block) == "the Forest"
    assert adopted_name("### P-2026-11-26-002 — Other\nProposed text:\nx") is None


def test_an_adopted_naming_proposal_names_the_current_civilization(cfg):
    civs = Civilizations(cfg)
    civs.start(["Pale Rest"])
    archive = cfg.memory_dir / "archive"
    archive.mkdir(parents=True, exist_ok=True)
    (archive / "promoted_proposals.md").write_text(
        "### P-2026-11-26-001 — Name the civilization: the Forest\nAuthor: Pale Rest\nMotivation: m\n"
        "Names the civilization: the Forest\nProposed text:\nThis civilization is named the Forest.\n\n"
        "Adopted 2026-11-26 with net 3 votes.\n\n"
        "### P-2026-11-26-002 — Something else\nAuthor: Pale Rest\nMotivation: m\nProposed text:\nx\n\n")
    assert apply_adopted_names(cfg, ["P-2026-11-26-002"]) == []
    assert apply_adopted_names(cfg, ["P-2026-11-26-001"]) == [(1, "the Forest")]
    assert civs.label(1) == "the Forest"
