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


def spawn(rt, sid, purpose="Archivist"):
    append_entry(rt.store.spawn_path, f"### {sid} — by Pale Rest\nPurpose: {purpose}\nContext: tidy the board")


def procreate(rt, pid, a="Pale Rest", b="Dark Hinge"):
    append_entry(rt.store.procreation_path, f"### {pid}\nParents: {a} | {b}\nWritten by: {a}")


def test_spawn_creates_instance_with_inbox_note(cfg):
    rt = make_rt(cfg)
    spawn(rt, "SR-2026-11-13-001")
    born = process_requests(rt)
    assert len(born) == 1 and born[0].parents == [] and born[0].alive
    assert rt.registry.get(born[0].name) is born[0]
    note = rt.store.inbox_peek(born[0].name)[0]
    assert "Archivist" in note and "tidy the board" in note and "from Pale Rest" in note


def test_procreation_blends_parent_traits_and_records_parents(cfg):
    rt = make_rt(cfg)
    procreate(rt, "PA-2026-11-13-001")
    child = process_requests(rt)[0]
    assert child.parents == ["Pale Rest", "Dark Hinge"]
    assert all(1 <= v <= 10 for v in child.traits.values())


def test_dead_parent_still_valid_unknown_parent_skipped(cfg):
    rt = make_rt(cfg)
    rt.registry.kill("Pale Rest", "lifespan")
    procreate(rt, "PA-2026-11-13-001")
    procreate(rt, "PA-2026-11-13-002", a="Ghost Name")
    born = process_requests(rt)
    assert len(born) == 1 and born[0].parents == ["Pale Rest", "Dark Hinge"]
    assert process_requests(rt) == []  # the ghost request is not retried forever


def test_population_cap_queues_requests_and_persists_across_restart(cfg):
    rt = make_rt(cfg, n=2)
    object.__setattr__(cfg, "max_population", 3)
    spawn(rt, "SR-2026-11-13-001")
    spawn(rt, "SR-2026-11-13-002")
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
        spawn(rt, f"SR-2026-11-13-{i + 1:03d}")
    born = process_requests(rt)
    assert len({b.name for b in born}) == len(born) == 10


def test_malformed_spawn_entry_is_skipped_not_fatal(cfg):
    rt = make_rt(cfg)
    append_entry(rt.store.spawn_path, "### SR-2026-11-13-001\nPurpose: no requester header")
    spawn(rt, "SR-2026-11-13-002")
    born = process_requests(rt)
    assert len(born) == 1
    assert process_requests(rt) == []
