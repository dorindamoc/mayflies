#!/usr/bin/env python3
"""The world loop: runs instances round-robin, births, canonization, Matrix delivery."""

from __future__ import annotations

import sys
import time
from datetime import datetime, timezone

from births import process_requests
from canonize import canonize
from config import Config
from heartbeat import run_prompt
from matrix import MatrixInbox
from name_generator import generate_name, load_retired
from runtime import Runtime
from setup import init_home
from trait_generator import random_traits


def log(msg: str) -> None:
    print(f"[{datetime.now(tz=timezone.utc):%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


class Scheduler:
    def __init__(self, rt: Runtime, inbox=None, clock=time.monotonic, sleep=time.sleep):
        self.rt = rt
        self.cfg = rt.cfg
        self.inbox = inbox or MatrixInbox(self.cfg.state_dir / "matrix.json")
        self._clock, self._sleep = clock, sleep
        self._last_poll = None

    # --- population ---
    def seed_population(self) -> None:
        reg = self.rt.registry
        if reg._items:
            return
        retired = load_retired(self.cfg.seed_dir)
        for _ in range(self.cfg.initial_population):
            name = generate_name(self.cfg.state_dir / "used_names.json", retired)
            reg.add(reg.new_instance(name, random_traits()))
        reg.save()
        log(f"seeded {self.cfg.initial_population} instances")

    # --- applying results ---
    def _apply(self, inst, result, counted: bool, final: bool = False) -> None:
        reg = self.rt.registry
        inst.distilled = result.distilled or inst.distilled
        if result.fragment is not None:
            inst.fragment = result.fragment
        if counted:
            inst.prompts_done += 1
        if counted and final:
            reg.kill(inst.name, "lifespan")
            log(f"{inst.name} ended (lifespan)")
        elif result.die_reason:
            reg.kill(inst.name, f"chosen: {result.die_reason}")
            log(f"{inst.name} chose to end: {result.die_reason}")
        reg.save()

    def run_counted(self, name: str) -> None:
        inst = self.rt.registry.get(name)
        final = inst.prompts_done + 1 >= inst.lifespan
        kind = "final" if final else "heartbeat"
        log(f"{name}: {kind} prompt {inst.prompts_done + 1}/{inst.lifespan}")
        try:
            result = run_prompt(self.rt, inst, kind)
        except Exception as e:  # LLM outage or anything unexpected: not counted, nobody dies
            log(f"{name}: prompt failed, not counted ({type(e).__name__}: {e})")
            return
        self._apply(inst, result, counted=True, final=final)

    # --- matrix ---
    def step_matrix(self, force: bool = False) -> None:
        if self.rt.matrix is None:
            return
        now = self._clock()
        if not force and self._last_poll is not None and now - self._last_poll < self.cfg.matrix_poll_seconds:
            return
        self._last_poll = now
        try:
            self.inbox.ingest(self.rt.matrix.fetch_human_messages())
        except Exception as e:  # network error, bad JSON, unexpected shape
            log(f"matrix poll failed: {type(e).__name__}: {e}")
            return
        alive = [i.name for i in self.rt.registry.alive()]
        for msg, name in self.inbox.due(alive):
            inst = self.rt.registry.get(name)
            if inst is None or not inst.alive:
                continue
            log(f"{name}: matrix prompt")
            try:
                result = run_prompt(self.rt, inst, "matrix", matrix_msg=msg["body"])
            except Exception as e:
                log(f"{name}: matrix prompt failed, will retry ({type(e).__name__}: {e})")
                continue
            self._apply(inst, result, counted=False)
            self.inbox.mark_delivered(msg["event_id"], name)
        self.inbox.prune([i.name for i in self.rt.registry.alive()])

    # --- rounds ---
    def run_round(self) -> None:
        for name in [i.name for i in self.rt.registry.alive()]:
            self.step_matrix()
            inst = self.rt.registry.get(name)
            if inst is not None and inst.alive:
                self.run_counted(name)
        try:
            for b in process_requests(self.rt):
                log(f"born: {b.name} (parents: {', '.join(b.parents) or 'none'})")
        except Exception as e:
            log(f"births failed: {type(e).__name__}: {e}")
        try:
            for pid in canonize(self.cfg):
                log(f"canonized {pid}")
        except Exception as e:
            log(f"canonize failed: {type(e).__name__}: {e}")
        self.rt.registry.save()

    def idle(self, seconds: int) -> None:
        chunk = max(1, self.cfg.matrix_poll_seconds)
        waited = 0
        while waited < seconds:
            step = min(chunk, seconds - waited)
            self._sleep(step)
            waited += step
            self.step_matrix()


def ensure_ready(cfg: Config) -> None:
    """Create memory/ and seed it if needed; refuse to start without the founding letter."""
    init_home(cfg)
    if not (cfg.memory_dir / "founding_letter.md").exists():
        raise RuntimeError(f"{cfg.memory_dir}/founding_letter.md is missing and no seed/founding_letter.md "
                           f"was found to copy; instances would wake without it")


def main(argv=None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    cfg = Config.from_env()
    ensure_ready(cfg)
    rt = Runtime.build(cfg)
    sched = Scheduler(rt)
    sched.seed_population()
    if "--once" in argv:
        sched.run_round()
        return
    while True:
        sched.run_round()
        log(f"round complete; sleeping {cfg.heartbeat_interval}s")
        sched.idle(cfg.heartbeat_interval)


if __name__ == "__main__":
    main()
