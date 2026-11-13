"""The population registry. Written only by the scheduler process."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Optional

from config import Config
from store import stamp


@dataclass
class Instance:
    name: str
    model: str
    traits: dict
    lifespan: int
    parents: list = field(default_factory=list)
    prompts_done: int = 0
    fragment: str = ""
    distilled: str = ""
    alive: bool = True
    died: str = ""
    born_at: str = ""


class Registry:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.path = cfg.state_dir / "instances.json"
        self._items: dict = {}
        if self.path.exists():
            for d in json.loads(self.path.read_text()):
                self._items[d["name"]] = Instance(**d)

    def new_instance(self, name: str, traits: dict, parents=()) -> Instance:
        return Instance(name=name, model=self.cfg.model_default, traits=dict(traits),
                        lifespan=self.cfg.lifespan_prompts, parents=list(parents), born_at=stamp())

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
                      f"- born: {i.born_at}", f"- prompt: {i.prompts_done + 1} of {i.lifespan}",
                      f"- parents: {parents}", ""]
        return "\n".join(lines)

    def world_state(self) -> str:
        alive = self.alive()
        rows = [f"{i.name} (prompt {i.prompts_done + 1} of {i.lifespan})" for i in alive]
        return (f"Population: {len(alive)} of {self.cfg.max_population} slots.\n"
                f"Alive: {', '.join(rows) if rows else 'no one'}.")
