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
    assert "2 of 20" in text and "Pale Rest (prompt 3)" in text and "Dark Hinge (prompt 1)" in text


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


def test_offspring_model_is_random_from_the_pool_not_inherited(cfg):
    r = Registry(weighted_cfg(cfg))
    a = r.new_instance("Aa", T, model="m-a")
    b = r.new_instance("Bb", T, model="m-a")
    picks = [r.pick_model([a, b], random.Random(s)) for s in range(400)]
    assert set(picks) == {"m-a", "m-b", "m-c", "big"} and picks.count("m-a") < 200  # not the parents' model


def test_records_from_before_the_memory_files_still_load(cfg):
    import json
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    (cfg.state_dir / "instances.json").write_text(json.dumps([{
        "name": "Pale Rest", "model": "qwen3.8:27b", "traits": T, "lifespan": 7, "parents": [],
        "prompts_done": 2, "fragment": "old", "distilled": "older", "alive": True, "died": "", "born_at": ""}]))
    assert Registry(cfg).get("Pale Rest").prompts_done == 2


def test_a_corrupt_registry_falls_back_to_the_last_good_copy(cfg):
    r = Registry(cfg)
    r.add(r.new_instance("Pale Rest", T))
    r.save()
    r.add(r.new_instance("Dark Hinge", T))
    r.save()  # the first save is now the backup
    cfg.state_dir.joinpath("instances.json").write_text('[{"name": "Pale')  # a torn write
    assert [i.name for i in Registry(cfg).alive()] == ["Pale Rest"]


def test_a_corrupt_registry_with_no_backup_is_an_error(cfg):
    import pytest
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    cfg.state_dir.joinpath("instances.json").write_text("{torn")
    with pytest.raises(ValueError):
        Registry(cfg)


def test_instances_know_their_civilization_and_when_they_died(cfg):
    r = Registry(cfg)
    r.add(r.new_instance("Pale Rest", T, civ=2))
    assert r.get("Pale Rest").civ == 2 and r.get("Pale Rest").died_at == ""
    r.kill("Pale Rest", "memory full")
    r.save()
    again = Registry(cfg).get("Pale Rest")
    assert again.civ == 2 and again.died_at


def test_an_old_registry_without_civ_loads_as_civilization_one(cfg):
    import json
    (cfg.state_dir).mkdir(parents=True, exist_ok=True)
    (cfg.state_dir / "instances.json").write_text(json.dumps([{"name": "Pale Rest", "model": "m", "traits": T}]))
    assert Registry(cfg).get("Pale Rest").civ == 1
