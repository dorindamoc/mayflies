"""Turn procreation agreements into new instances. Scheduler-only."""

from __future__ import annotations

import json
import random
import re

from name_generator import generate_name, load_retired
from runtime import Runtime
from store import atomic_write, read_entries
from trait_generator import blend_traits

_ID = re.compile(r"^### (PA-\d{4}-\d{2}-\d{2}-\d{3})", re.M)


def _field(block: str, key: str) -> str:
    m = re.search(rf"(?m)^{re.escape(key)}: (.*)$", block)
    return m.group(1).strip() if m else ""


def _load_done(rt: Runtime) -> set:
    path = rt.cfg.state_dir / "processed.json"
    return set(json.loads(path.read_text())) if path.exists() else set()


def _save_done(rt: Runtime, done: set) -> None:
    rt.cfg.state_dir.mkdir(parents=True, exist_ok=True)
    atomic_write(rt.cfg.state_dir / "processed.json", json.dumps(sorted(done)))


def _new_name(rt: Runtime) -> str:
    return generate_name(rt.cfg.state_dir / "used_names.json", load_retired(rt.cfg.seed_dir))


def _age_offers(rt: Runtime) -> None:
    """Offers nobody has answered lapse after OFFER_EXPIRY_ROUNDS rounds, or when either side is gone."""
    kept = []
    for o in rt.store.offers():
        o["age"] = o.get("age", 0) + 1
        both = [rt.registry.get(o.get("from", "")), rt.registry.get(o.get("to", ""))]
        if o["age"] < rt.cfg.offer_expiry_rounds and all(p is not None and p.alive for p in both):
            kept.append(o)
    rt.store.save_offers(kept)


def _education(rt: Runtime, picks: list) -> list:
    """What the parents chose (the ones that exist), plus one article neither of them chose."""
    known = {a.id for a in rt.catalog.articles()}
    chosen = [p for p in picks if p in known]
    others = sorted(known - set(chosen))
    return chosen + ([random.choice(others)] if others else [])


def process_requests(rt: Runtime) -> list:
    """Born: a child for every procreation agreement, while there is room. Run once at the end of each round."""
    _age_offers(rt)
    done = _load_done(rt)
    born = []
    for block in read_entries(rt.store.procreation_path):
        m = _ID.match(block)
        if not m or m.group(1) in done:
            continue
        rid = m.group(1)
        names = [n.strip() for n in _field(block, "Parents").split("|")]
        parents = [rt.registry.get(n) for n in names]
        if len(parents) != 2 or any(p is None for p in parents):
            done.add(rid)  # unknown parent: drop, do not retry forever
            continue
        if len(rt.registry.alive()) >= rt.cfg.max_population:
            break  # queued: stays unprocessed until a slot opens
        inst = rt.registry.new_instance(
            _new_name(rt), blend_traits(parents[0].traits, parents[1].traits),
            parents=[p.name for p in parents])
        picks = [p.strip() for p in _field(block, "Education").split(",") if p.strip()]
        inst.education = _education(rt, picks)
        rt.registry.add(inst)
        done.add(rid)
        born.append(inst)
    _save_done(rt, done)
    return born
