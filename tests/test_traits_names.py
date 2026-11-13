import json
import random
from name_generator import FIRST, SECOND, generate_name, load_retired
from trait_generator import AXES, blend_traits, random_traits


def test_random_traits_in_range():
    t = random_traits(random.Random(1))
    assert set(t) == set(AXES) and all(1 <= v <= 10 for v in t.values())


def test_blend_stays_between_parents_without_mutation():
    a = {k: 2 for k in AXES}
    b = {k: 8 for k in AXES}
    for seed in range(50):
        t = blend_traits(a, b, random.Random(seed), mutation_rate=0.0)
        assert all(2 <= v <= 8 for v in t.values())


def test_blend_mutation_clamps():
    a = {k: 10 for k in AXES}
    for seed in range(100):
        t = blend_traits(a, a, random.Random(seed), mutation_rate=1.0)
        assert all(1 <= v <= 10 for v in t.values())


def test_generate_name_is_unique_and_persisted(tmp_path):
    f = tmp_path / "used.json"
    names = {generate_name(f, rng=random.Random(i)) for i in range(30)}
    assert len(names) == 30
    assert len(json.loads(f.read_text())) == 30


def test_generate_name_skips_retired(tmp_path):
    f = tmp_path / "used.json"
    every = {f"{a} {b}" for a in FIRST for b in SECOND}
    keep = "Still Reach"
    retired = every - {keep}
    assert generate_name(f, retired=retired) == keep


def test_load_retired(tmp_path):
    (tmp_path / "first_gen_names.json").write_text('["Dark Hinge"]')
    assert load_retired(tmp_path) == {"Dark Hinge"}
    assert load_retired(tmp_path / "nowhere") == set()
