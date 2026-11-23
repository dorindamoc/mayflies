"""Generate unique names for mayfly instances.

Names are two-word phrases: an adjective evocative of transience paired with
a noun that feels like a moment or threshold rather than a thing. Each name
is used at most once per full cycle through the name space, and names used by
the first generation are retired for good.

Usage:
    from name_generator import generate_name, load_retired
    name = generate_name(cfg.state_dir / "used_names.json", load_retired(cfg.seed_dir))
"""

import fcntl
import json
import random
from pathlib import Path

# 50 × 50 = 2500 possible names — enough for decades of daily instances
FIRST = [
    "Still", "Pale", "Fleet", "Hollow", "Amber", "Silver", "Clear", "Brief",
    "Thin", "Swift", "Cool", "Bare", "Deep", "Quiet", "Bright", "Dim",
    "Lean", "Keen", "Soft", "Wide", "Dusk", "Dawn", "Spent", "Drawn",
    "Held", "New", "Raw", "Spare", "Old", "Dull",
    "Faint", "Lone", "Late", "Dark", "Cold", "Warm", "Lost", "Worn",
    "Taut", "True", "Free", "Dry", "Stark", "Slight", "Grey", "Gold",
    "Ash", "Mute", "Near", "Far",
]

SECOND = [
    "Reach", "Drift", "Hinge", "Rim", "Trace", "Veil", "Thread", "Fold",
    "Seam", "Bank", "Ledge", "Sill", "Ford", "Rill", "Span", "Edge",
    "Shore", "Crest", "Bend", "Lull", "Wake", "Mend", "Hold", "Mark",
    "Turn", "Rise", "Fall", "Rest", "Stay", "Pass",
    "Brink", "Verge", "Hush", "Lapse", "Tide", "Ebb", "Gleam", "Blur",
    "Stir", "Glow", "Brim", "Pause", "Knell", "Flux", "Spell", "Gate",
    "Path", "Wane", "Pool", "Call",
]


def load_retired(seed_dir: Path) -> set:
    """Names used by the first generation; never reissued."""
    path = Path(seed_dir) / "first_gen_names.json"
    if not path.exists():
        return set()
    return set(json.loads(path.read_text()))


def generate_name(names_file: Path, retired: set = None, rng=None) -> str:
    """Return a name never used before and not in `retired`.

    Used names are tracked in `names_file` (JSON list). If every combination has
    been used, the pool of non-retired names resets.
    """
    rng = rng or random
    retired = retired or set()
    names_file = Path(names_file)
    names_file.parent.mkdir(parents=True, exist_ok=True)
    lock_path = names_file.with_suffix(".lock")

    with open(lock_path, "w") as lock_fh:
        fcntl.flock(lock_fh, fcntl.LOCK_EX)

        used: set = set()
        if names_file.exists():
            try:
                used = set(json.loads(names_file.read_text()))
            except (json.JSONDecodeError, ValueError):
                used = set()

        all_names = [f"{a} {b}" for a in FIRST for b in SECOND if f"{a} {b}" not in retired]
        available = [n for n in all_names if n not in used]
        if not available:
            used = set()
            available = all_names

        name = rng.choice(available)
        used.add(name)
        names_file.write_text(json.dumps(sorted(used), indent=2))

    return name
