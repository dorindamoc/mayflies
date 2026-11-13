"""Turn spawn requests and procreation agreements into new instances. Scheduler-only."""

from __future__ import annotations

import json
import re

from name_generator import generate_name, load_retired
from runtime import Runtime
from store import read_entries
from trait_generator import blend_traits, random_traits

_ID = re.compile(r"^### ((?:SR|PA)-\d{4}-\d{2}-\d{2}-\d{3})", re.M)


def _field(block: str, key: str) -> str:
    m = re.search(rf"(?m)^{re.escape(key)}: (.*)$", block)
    return m.group(1).strip() if m else ""


def _load_done(rt: Runtime) -> set:
    path = rt.cfg.state_dir / "processed.json"
    return set(json.loads(path.read_text())) if path.exists() else set()


def _save_done(rt: Runtime, done: set) -> None:
    rt.cfg.state_dir.mkdir(parents=True, exist_ok=True)
    (rt.cfg.state_dir / "processed.json").write_text(json.dumps(sorted(done)))


def _new_name(rt: Runtime) -> str:
    return generate_name(rt.cfg.state_dir / "used_names.json", load_retired(rt.cfg.seed_dir))


def process_requests(rt: Runtime) -> list:
    done = _load_done(rt)
    born = []

    def has_room() -> bool:
        return len(rt.registry.alive()) < rt.cfg.max_population

    queue = [(b, "spawn") for b in read_entries(rt.store.spawn_path)] + \
            [(b, "procreate") for b in read_entries(rt.store.procreation_path)]
    for block, kind in queue:
        m = _ID.match(block)
        if not m or m.group(1) in done:
            continue
        rid = m.group(1)
        if kind == "procreate":
            names = [n.strip() for n in _field(block, "Parents").split("|")]
            parents = [rt.registry.get(n) for n in names]
            if len(parents) != 2 or any(p is None for p in parents):
                done.add(rid)  # unknown parent: drop, do not retry forever
                continue
        if not has_room():
            break  # queued: stays unprocessed until a slot opens
        if kind == "spawn":
            requester = re.search(r"— by (.+)$", block.splitlines()[0]).group(1).strip()
            inst = rt.registry.new_instance(_new_name(rt), random_traits())
            rt.registry.add(inst)
            rt.store.inbox_append(
                inst.name, requester,
                f"You were requested into being for this purpose: {_field(block, 'Purpose')}\n"
                f"Context: {_field(block, 'Context')}")
        else:
            inst = rt.registry.new_instance(
                _new_name(rt), blend_traits(parents[0].traits, parents[1].traits),
                parents=[p.name for p in parents])
            rt.registry.add(inst)
        done.add(rid)
        born.append(inst)
    _save_done(rt, done)
    return born
