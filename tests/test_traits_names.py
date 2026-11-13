import json
import random
from name_generator import FIRST, SECOND, generate_name, load_retired
from trait_generator import AXES, blend_traits, describe_traits, random_traits, sampling_options


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


def test_describe_traits_uses_prose_only_for_extremes():
    mid = {k: 5 for k in AXES}
    assert "balanced" in describe_traits(mid)
    hi = dict(mid, skepticism=10)
    lo = dict(mid, skepticism=1)
    assert describe_traits(hi) != describe_traits(lo)
    assert "doubt" in describe_traits(hi) and "face value" in describe_traits(lo)
    assert "balanced" not in describe_traits(hi)


def test_sampling_options_follow_traits_within_bounds():
    wild = {"optimism": 5, "skepticism": 5, "artistry": 10, "exploration": 10, "decisiveness": 1}
    calm = {"optimism": 5, "skepticism": 5, "artistry": 1, "exploration": 1, "decisiveness": 10}
    w = sampling_options(wild, 0.6, 1.1, 0.5)
    c = sampling_options(calm, 0.6, 1.1, 0.5)
    assert c["temperature"] == 0.6 and w["temperature"] == 1.1
    assert w["presence_penalty"] == c["presence_penalty"] == 0.5
    mid = sampling_options({k: 5 for k in AXES}, 0.6, 1.1, 0.5)
    assert 0.6 < mid["temperature"] < 1.1
