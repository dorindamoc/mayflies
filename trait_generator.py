"""Personality traits: random assignment at birth, blending for offspring."""

from __future__ import annotations

import random

AXES = ("optimism", "skepticism", "artistry", "exploration", "decisiveness")


def _clamp(v: int) -> int:
    return max(1, min(10, v))


def random_traits(rng: random.Random | None = None) -> dict[str, int]:
    rng = rng or random
    return {axis: rng.randint(1, 10) for axis in AXES}


def blend_traits(a: dict[str, int], b: dict[str, int],
                 rng: random.Random | None = None, mutation_rate: float = 0.1) -> dict[str, int]:
    """Per axis: a uniformly random value between the parents' values (inclusive),
    with a `mutation_rate` chance of a +-1 or +-2 shift. Always clamped to 1-10."""
    rng = rng or random
    out = {}
    for axis in AXES:
        lo, hi = sorted((a[axis], b[axis]))
        v = rng.randint(lo, hi)
        if rng.random() < mutation_rate:
            v += rng.choice([-2, -1, 1, 2])
        out[axis] = _clamp(v)
    return out
