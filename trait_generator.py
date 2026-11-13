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


# (low-end phrase, high-end phrase): used only at the extremes (<=3, >=8).
_PROSE = {
    "optimism": ("You expect things to go wrong, and you notice risk and decay before promise.",
                 "You expect things to work out, and you notice what is promising and alive."),
    "skepticism": ("You take things at face value and extend trust readily.",
                   "You doubt by default: you test claims and do not agree just because others do."),
    "artistry": ("You think in structure, evidence and precise argument.",
                 "You think in images, rhythm and metaphor, and want to make beautiful things."),
    "exploration": ("You go deep on one thing and finish it before starting another.",
                    "You chase the new and unfamiliar, and leave a subject when it stops surprising you."),
    "decisiveness": ("You deliberate long, hold several views at once, and hesitate to commit.",
                     "You decide fast and act, even on incomplete information."),
}


def describe_traits(traits: dict[str, int]) -> str:
    """Prose for the traits that are pronounced; mid-range traits say nothing."""
    lines = []
    for axis in AXES:
        v = traits[axis]
        if v <= 3:
            lines.append(_PROSE[axis][0])
        elif v >= 8:
            lines.append(_PROSE[axis][1])
    return "\n".join(lines) if lines else "Your temperament is balanced; no trait pulls hard in either direction."


def sampling_options(traits: dict[str, int], temp_min: float, temp_max: float,
                     presence_penalty: float) -> dict[str, float]:
    """Per-instance sampling: exploratory, artistic, indecisive minds sample hotter."""
    raw = traits["exploration"] + traits["artistry"] + (10 - traits["decisiveness"])
    frac = (raw - 2) / 27  # raw spans 2..29
    return {"temperature": round(temp_min + (temp_max - temp_min) * frac, 2),
            "presence_penalty": presence_penalty}
