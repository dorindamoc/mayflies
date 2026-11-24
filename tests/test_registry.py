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
    assert "2 of 10" in text and "Pale Rest (prompt 3)" in text and "Dark Hinge (prompt 1)" in text


import random
from collections import Counter
from dataclasses import replace


def weighted_cfg(cfg):
    return replace(cfg, model_pool=("m-a", "m-b", "m-c", "big"), model_weights={"m-a": 3, "m-b": 3, "m-c": 3, "big": 1})


def test_new_instances_follow_the_pool_weights(cfg):
    r = Registry(weighted_cfg(cfg))
    for i in range(10):
        r.add(r.new_instance(f"Name {'abcdefghij'[i]}", T))
    assert Counter(i.model for i in r.alive()) == {"m-a": 3, "m-b": 3, "m-c": 3, "big": 1}


def test_offspring_inherit_a_parents_model_unless_mutating(cfg):
    r = Registry(weighted_cfg(cfg))
    a = r.new_instance("Aa", T, model="m-a")
    b = r.new_instance("Bb", T, model="m-b")
    assert {r.pick_model([a, b], random.Random(s), mutation_rate=0.0) for s in range(40)} == {"m-a", "m-b"}
    assert {r.pick_model([a, b], random.Random(s), mutation_rate=1.0) for s in range(300)} == {"m-a", "m-b", "m-c", "big"}


def test_records_from_before_the_memory_files_still_load(cfg):
    import json
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    (cfg.state_dir / "instances.json").write_text(json.dumps([{
        "name": "Pale Rest", "model": "qwen3.8:27b", "traits": T, "lifespan": 7, "parents": [],
        "prompts_done": 2, "fragment": "old", "distilled": "older", "alive": True, "died": "", "born_at": ""}]))
    assert Registry(cfg).get("Pale Rest").prompts_done == 2
