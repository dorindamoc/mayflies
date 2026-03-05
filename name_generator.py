"""Generate unique names for mayfly instances.

Names are two-word phrases: an adjective evocative of transience paired with
a noun that feels like a moment or threshold rather than a thing. Each name
is used at most once per full cycle through the name space.

Usage:
    from name_generator import generate_name
    name = generate_name()  # e.g. "Pale Reach"
"""

import fcntl
import json
import random
from pathlib import Path

BASE_DIR = Path(__file__).parent
NAMES_FILE = BASE_DIR / "memory" / "used_names.json"

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


def generate_name() -> str:
    """Return a unique name, tracking used names in memory/used_names.json.

    If all 2500 combinations have been used, resets the pool and starts over.
    Uses file locking to handle concurrent instantiation safely.
    """
    NAMES_FILE.parent.mkdir(exist_ok=True)
    lock_path = NAMES_FILE.with_suffix(".lock")

    with open(lock_path, "w") as lock_fh:
        fcntl.flock(lock_fh, fcntl.LOCK_EX)

        used: set[str] = set()
        if NAMES_FILE.exists():
            try:
                used = set(json.loads(NAMES_FILE.read_text()))
            except (json.JSONDecodeError, ValueError):
                used = set()

        all_names = [f"{a} {b}" for a in FIRST for b in SECOND]
        available = [n for n in all_names if n not in used]

        if not available:
            # Full cycle complete — start over
            used = set()
            available = all_names

        name = random.choice(available)
        used.add(name)
        NAMES_FILE.write_text(json.dumps(sorted(used), indent=2))

    return name
