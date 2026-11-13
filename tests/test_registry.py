from registry import Registry
from trait_generator import AXES

T = {k: 5 for k in AXES}


def test_add_save_reload_and_order(cfg):
    r = Registry(cfg)
    r.add(r.new_instance("Pale Rest", T))
    r.add(r.new_instance("Dark Hinge", T))
    r.save()
    r2 = Registry(cfg)
    assert [i.name for i in r2.alive()] == ["Pale Rest", "Dark Hinge"]
    assert r2.get("Pale Rest").lifespan == cfg.lifespan_prompts


def test_kill_frees_slot_but_keeps_record(cfg):
    r = Registry(cfg)
    r.add(r.new_instance("Pale Rest", T))
    r.kill("Pale Rest", "chosen: done")
    r.save()
    assert r.alive() == []
    dead = Registry(cfg).get("Pale Rest")
    assert dead is not None and dead.alive is False and dead.died == "chosen: done"


def test_registry_md_lists_only_alive(cfg):
    r = Registry(cfg)
    r.add(r.new_instance("Pale Rest", T))
    r.add(r.new_instance("Dark Hinge", T))
    r.kill("Dark Hinge", "lifespan")
    r.save()
    md = (cfg.memory_dir / "registry.md").read_text()
    assert "Pale Rest" in md and "Dark Hinge" not in md


def test_world_state_mentions_population_and_positions(cfg):
    r = Registry(cfg)
    a = r.new_instance("Pale Rest", T); a.prompts_done = 2
    r.add(a)
    r.add(r.new_instance("Dark Hinge", T))
    text = r.world_state()
    assert "2 of 10" in text and "Pale Rest (prompt 3 of 7)" in text and "Dark Hinge (prompt 1 of 7)" in text
