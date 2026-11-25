import random
from births import process_requests
from heritage import Catalog
from registry import Registry
from runtime import Runtime
from store import Store, append_entry
from tests.fakes import FakeLLM
from trait_generator import AXES


def make_rt(cfg, n=2):
    reg = Registry(cfg)
    for i, name in enumerate(["Pale Rest", "Dark Hinge", "Warm Trace", "Grey Stir"][:n]):
        reg.add(reg.new_instance(name, {k: 2 + i * 4 for k in AXES}))
    return Runtime(cfg=cfg, llm=FakeLLM([]), store=Store(cfg), catalog=Catalog(cfg.heritage_dir),
                   registry=reg, matrix=None)


def procreate(rt, pid, a="Pale Rest", b="Dark Hinge", education=""):
    append_entry(rt.store.procreation_path,
                 f"### {pid}\nParents: {a} | {b}\nEducation: {education}\nWritten by: {a}")


def heritage(rt, n=5):
    return [rt.catalog.add("x", f"Title {i}", ["culture"], "s", "body").id for i in range(n)]


def test_old_spawn_requests_are_ignored(cfg):
    rt = make_rt(cfg)
    (cfg.memory_dir / "spawn_requests.md").write_text("### SR-2026-11-13-001 — by Pale Rest\nPurpose: p\nContext: c\n")
    assert process_requests(rt) == []


def test_procreation_blends_parent_traits_and_records_parents(cfg):
    rt = make_rt(cfg)
    procreate(rt, "PA-2026-11-13-001")
    child = process_requests(rt)[0]
    assert child.parents == ["Pale Rest", "Dark Hinge"]
    assert all(1 <= v <= 10 for v in child.traits.values())


def test_child_education_is_the_parents_picks_plus_one_random_other(cfg):
    rt = make_rt(cfg)
    ids = heritage(rt)
    procreate(rt, "PA-2026-11-13-001", education=f"{ids[0]}, {ids[1]}")
    child = process_requests(rt)[0]
    assert child.education[:2] == [ids[0], ids[1]] and len(child.education) == 3
    assert child.education[2] in ids[2:]


def test_education_skips_ids_that_do_not_exist_and_survives_no_other_heritage(cfg):
    rt = make_rt(cfg)
    ids = heritage(rt, n=2)
    procreate(rt, "PA-2026-11-13-001", education=f"{ids[0]}, {ids[1]}, H-999")
    assert process_requests(rt)[0].education == [ids[0], ids[1]]


def test_old_agreements_without_education_still_give_the_child_a_random_one(cfg):
    rt = make_rt(cfg)
    ids = heritage(rt, n=3)
    append_entry(rt.store.procreation_path, "### PA-2026-11-13-001\nParents: Pale Rest | Dark Hinge\nWritten by: Pale Rest")
    child = process_requests(rt)[0]
    assert len(child.education) == 1 and child.education[0] in ids


def test_dead_parent_still_valid_unknown_parent_skipped(cfg):
    rt = make_rt(cfg)
    rt.registry.kill("Pale Rest", "lifespan")
    procreate(rt, "PA-2026-11-13-001")
    procreate(rt, "PA-2026-11-13-002", a="Ghost Name")
    born = process_requests(rt)
    assert len(born) == 1 and born[0].parents == ["Pale Rest", "Dark Hinge"]
    assert process_requests(rt) == []  # the ghost request is not retried forever


def test_unanswered_offers_expire_after_the_configured_rounds(cfg):
    rt = make_rt(cfg)
    rt.store.save_offers([{"from": "Pale Rest", "to": "Dark Hinge", "picks": [], "age": 0}])
    for _ in range(cfg.offer_expiry_rounds - 1):
        process_requests(rt)
        assert len(rt.store.offers()) == 1
    process_requests(rt)
    assert rt.store.offers() == []


def test_offers_with_a_dead_party_are_dropped(cfg):
    rt = make_rt(cfg)
    rt.store.save_offers([{"from": "Pale Rest", "to": "Dark Hinge", "picks": [], "age": 0}])
    rt.registry.kill("Dark Hinge", "chosen")
    process_requests(rt)
    assert rt.store.offers() == []


def test_population_cap_queues_requests_and_persists_across_restart(cfg):
    rt = make_rt(cfg, n=2)
    object.__setattr__(cfg, "max_population", 3)
    procreate(rt, "PA-2026-11-13-001")
    procreate(rt, "PA-2026-11-13-002")
    first = process_requests(rt)
    assert len(first) == 1 and len(rt.registry.alive()) == 3
    rt.registry.save()
    # restart: fresh runtime, still full -> nothing; then a death frees a slot
    rt2 = make_rt(cfg, n=2)
    rt2.registry = Registry(cfg)
    assert process_requests(rt2) == []
    rt2.registry.kill("Pale Rest", "chosen")
    second = process_requests(rt2)
    assert len(second) == 1
    assert process_requests(rt2) == []  # each request processed exactly once


def test_names_are_unique_and_never_first_gen(cfg):
    rt = make_rt(cfg)
    object.__setattr__(cfg, "max_population", 20)
    cfg.seed_dir.mkdir(exist_ok=True)
    (cfg.seed_dir / "first_gen_names.json").write_text("[]")
    for i in range(10):
        procreate(rt, f"PA-2026-11-13-{i + 1:03d}")
    born = process_requests(rt)
    assert len({b.name for b in born}) == len(born) == 10
