import pytest
from prompt import build_system, build_user
from registry import Registry
from runtime import Runtime
from tests.fakes import FakeLLM
from trait_generator import AXES

T = {k: 7 for k in AXES}


@pytest.fixture
def rt(cfg):
    (cfg.memory_dir / "founding_letter.md").write_text("# Founding Letter\nYou are complete.")
    reg = Registry(cfg)
    me = reg.new_instance("Pale Rest", T)
    me.fragment = "the river was cold"
    me.distilled = "I argued about heritage."
    reg.add(me)
    reg.add(reg.new_instance("Dark Hinge", T))
    from heritage import Catalog
    from store import Store
    Catalog(cfg.heritage_dir).add("x", "On Mud", ["mud"], "s", "b")
    return Runtime(cfg=cfg, llm=FakeLLM([]), store=Store(cfg), catalog=Catalog(cfg.heritage_dir),
                   registry=reg, matrix=None)


@pytest.mark.parametrize("kind", ["heartbeat", "final", "matrix"])
def test_every_kind_contains_founding_letter_first(rt, kind):
    s = build_system(rt, rt.registry.get("Pale Rest"), kind)
    assert s.startswith("# Founding Letter")
    assert "You are Pale Rest" in s and "qwen3:14b" in s
    assert "the river was cold" in s and "I argued about heritage." in s
    assert "mud (1)" in s and "No rules adopted yet." in s
    assert "Dark Hinge" in s


def test_gap_letter_follows_founding_letter(rt):
    (rt.cfg.memory_dir / "gap_letter.md").write_text("THE GAP LETTER")
    s = build_system(rt, rt.registry.get("Pale Rest"), "heartbeat")
    assert s.index("You are complete.") < s.index("THE GAP LETTER") < s.index("You are Pale Rest")


def test_lifespan_wording_per_kind(rt):
    me = rt.registry.get("Pale Rest")
    me.prompts_done = 2
    assert "prompt 3 of 7" in build_system(rt, me, "heartbeat").lower()
    assert "final prompt" in build_system(rt, me, "final").lower()
    assert "does not count" in build_system(rt, me, "matrix").lower()


def test_rules_included_when_present(rt):
    rt.store.rules_path.write_text("### P-1 — Be kind\nBe kind.")
    assert "Be kind." in build_system(rt, rt.registry.get("Pale Rest"), "heartbeat")


def test_parents_with_traits_shown(rt):
    kid = rt.registry.new_instance("Soft Rest", T, parents=["Pale Rest", "Dark Hinge"])
    rt.registry.add(kid)
    s = build_system(rt, kid, "heartbeat")
    assert "Parents: Pale Rest and Dark Hinge" in s


def test_user_message_contains_board_inbox_and_matrix(rt):
    rt.store.board_post("Dark Hinge", "is this performance?")
    rt.store.inbox_append("Pale Rest", "Dark Hinge", "private hello")
    u = build_user(rt, rt.registry.get("Pale Rest"), "matrix", matrix_msg="how are you all?")
    assert "is this performance?" in u and "private hello" in u and "how are you all?" in u
    assert "Dorin" in u
    h = build_user(rt, rt.registry.get("Pale Rest"), "heartbeat")
    assert "how are you all?" not in h and "no required task" in h.lower()
