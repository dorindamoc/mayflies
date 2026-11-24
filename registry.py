"""The population registry. Written only by the scheduler process."""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass, field, fields
from typing import Optional

from config import Config
from store import stamp


@dataclass
class Instance:
    name: str
    model: str
    traits: dict
    parents: list = field(default_factory=list)
    prompts_done: int = 0
    alive: bool = True
    died: str = ""
    born_at: str = ""


class Registry:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.path = cfg.state_dir / "instances.json"
        self._items: dict = {}
        if self.path.exists():
            known = {f.name for f in fields(Instance)}
            for d in json.loads(self.path.read_text()):
                self._items[d["name"]] = Instance(**{k: v for k, v in d.items() if k in known})

    def pick_model(self, parents=(), rng=None, mutation_rate: float = 0.15) -> str:
        """Offspring inherit a parent's model (small chance of a weighted-random one); everyone else gets
        the pool model furthest below its weighted share of the living population."""
        rng = rng or random
        pool = self.cfg.models
        weights = [self.cfg.model_weights.get(m, 1) for m in pool]
        parents = [p for p in parents if p is not None and p.model]
        if parents:
            if rng.random() < mutation_rate:
                return rng.choices(pool, weights=weights)[0]
            return rng.choice(parents).model
        alive = self.alive()
        total = sum(weights)
        deficit = {m: w / total * (len(alive) + 1) - sum(1 for i in alive if i.model == m)
                   for m, w in zip(pool, weights)}
        best = max(deficit.values())
        return rng.choice([m for m in pool if deficit[m] >= best - 1e-9])

    def new_instance(self, name: str, traits: dict, parents=(), model: str = None) -> Instance:
        if model is None:
            model = self.pick_model([self.get(p) if isinstance(p, str) else p for p in parents])
        return Instance(name=name, model=model, traits=dict(traits),
                        parents=list(parents), born_at=stamp())

    def add(self, inst: Instance) -> None:
        self._items[inst.name] = inst

    def get(self, name: str) -> Optional[Instance]:
        return self._items.get(name)

    def alive(self) -> list:
        return [i for i in self._items.values() if i.alive]

    def kill(self, name: str, cause: str) -> None:
        inst = self._items[name]
        inst.alive = False
        inst.died = cause

    def save(self) -> None:
        self.cfg.state_dir.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps([asdict(i) for i in self._items.values()], indent=2))
        (self.cfg.memory_dir / "registry.md").write_text(self.render_markdown())

    def render_markdown(self) -> str:
        lines = ["# Registry", "", f"Alive: {len(self.alive())} of {self.cfg.max_population}", ""]
        for i in self.alive():
            t = ", ".join(f"{k} {v}" for k, v in i.traits.items())
            parents = " + ".join(i.parents) if i.parents else "none"
            lines += [f"## {i.name}", f"- model: {i.model}", f"- traits: {t}",
                      f"- born: {i.born_at}", f"- prompt: {i.prompts_done + 1}",
                      f"- parents: {parents}", ""]
        return "\n".join(lines)

    def world_state(self) -> str:
        alive = self.alive()
        rows = [f"{i.name} (prompt {i.prompts_done + 1})" for i in alive]
        return (f"Population: {len(alive)} of {self.cfg.max_population} slots.\n"
                f"Alive: {', '.join(rows) if rows else 'no one'}.")
