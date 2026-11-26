#!/usr/bin/env python3
"""The world loop: runs instances round-robin, births, canonization, Matrix delivery."""

from __future__ import annotations

import json
import signal
import sys
import time
from datetime import datetime, timezone

from births import process_requests
from canonize import canonize
from chronicle import write_pages, write_story
from civs import Civilizations, apply_adopted_names, archive_civilization
from config import Config
from distiller import fold
from heartbeat import run_prompt
from matrix import MatrixInbox
from publish import Publisher
from name_generator import generate_name, load_retired
from runtime import Runtime
from store import atomic_write
from setup import init_home
from trait_generator import random_traits


def log(msg: str) -> None:
    print(f"[{datetime.now(tz=timezone.utc):%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


class Scheduler:
    def __init__(self, rt: Runtime, inbox=None, clock=time.monotonic, sleep=time.sleep, publisher=None):
        self.rt = rt
        self.cfg = rt.cfg
        self.inbox = inbox or MatrixInbox(self.cfg.state_dir / "matrix.json")
        self._clock, self._sleep = clock, sleep
        self._last_poll = None
        self._stop = False
        self.publisher = publisher if publisher is not None else (
            Publisher(self.cfg) if self.cfg.website_publish else None)

    # --- stopping ---
    @property
    def stopping(self) -> bool:
        return self._stop

    def request_stop(self) -> None:
        """Finish the prompt in progress, then stop; nothing is cut off midway."""
        self._stop = True

    def handle_signal(self, signum, frame) -> None:
        if self._stop:
            log("second stop signal: exiting now; the prompt in progress will be repeated on restart")
            raise SystemExit(1)
        log("stop requested: finishing the current prompt, then stopping (signal again to exit at once)")
        self.request_stop()

    # --- progress through a round, so a restart continues it ---
    @property
    def _round_path(self):
        return self.cfg.state_dir / "round.json"

    def _load_round(self) -> set:
        try:
            return set(json.loads(self._round_path.read_text())["done"])
        except (OSError, ValueError, KeyError, TypeError):
            return set()

    def _save_round(self, done: set) -> None:
        atomic_write(self._round_path, json.dumps({"done": sorted(done)}))

    # --- population ---
    def seed_population(self) -> None:
        reg = self.rt.registry
        Civilizations(self.cfg).ensure_started(reg)  # a population that predates civilizations is civilization 1
        if reg._items:
            return
        self._found_civilization()

    def _found_civilization(self) -> None:
        reg, civs = self.rt.registry, Civilizations(self.cfg)
        cid = len(civs.records()) + 1
        retired = load_retired(self.cfg.seed_dir)
        names = []
        for _ in range(self.cfg.initial_population):
            name = generate_name(self.cfg.state_dir / "used_names.json", retired)
            reg.add(reg.new_instance(name, random_traits(), civ=cid))
            names.append(name)
        civs.start(names)
        reg.save()
        self._write_pages()
        log(f"seeded {self.cfg.initial_population} instances (civilization {cid})")

    def _write_pages(self, cid: int = None) -> None:
        try:
            write_pages(self.rt, cid)
        except Exception as e:  # the website pages must never stop the world
            log(f"civilization pages failed: {type(e).__name__}: {e}")

    def _check_extinction(self) -> None:
        civs = Civilizations(self.cfg)
        cur = civs.current()
        if cur is None or self.rt.registry.alive():
            return
        cid = cur["id"]
        civs.close(cid, "extinct")  # first, so the story knows how and when it ended
        try:
            story = write_story(self.rt, cid)
            civs.set_story(cid, story)
        except Exception as e:
            log(f"the story of civilization {cid} could not be written: {type(e).__name__}: {e}")
            story = ""
        self._write_pages(cid)
        log(f"civilization {cid} ({civs.label(cid)}) has ended; its story is {story or 'not written'}")
        if not self.cfg.restart_on_extinction:
            return
        if len(civs.records()) >= self.cfg.max_civilizations:
            log(f"not restarting: {self.cfg.max_civilizations} civilizations have lived")
            return
        archive_civilization(self.cfg, cid)
        self._found_civilization()

    # --- applying results ---
    def _apply(self, inst, result, counted: bool, final: bool = False) -> None:
        reg = self.rt.registry
        self._remember(inst, result)
        if counted:
            inst.prompts_done += 1
        if counted and final:
            reg.kill(inst.name, "memory full")
            log(f"{inst.name} ended (memory full)")
        elif result.die_reason:
            reg.kill(inst.name, f"chosen: {result.die_reason}")
            log(f"{inst.name} chose to end: {result.die_reason}")
        reg.save()

    def _remember(self, inst, result) -> None:
        """The last prompt's short-term memory is compacted into long-term; this prompt becomes the short-term."""
        mem = self.rt.memories
        before = mem.short_text(inst.name)
        if before:
            mem.append_long(inst.name, fold(self.rt.llm, self.cfg, inst, before))
        mem.set_short(inst.name, result.recap, result.fragment or "")

    def run_counted(self, name: str) -> None:
        inst = self.rt.registry.get(name)
        final = self.rt.memories.is_full(name)
        kind = "final" if final else "heartbeat"
        log(f"{name}: {kind} prompt {inst.prompts_done + 1} (long-term memory {int(self.rt.memories.fill(name) * 100)}%)")
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
        # only instances that finished their first (reading) prompt are written to
        educated = [i.name for i in self.rt.registry.alive() if i.prompts_done >= 1]
        for msg, name in self.inbox.due(educated, alive):
            if self.stopping:
                break
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
        done = self._load_round()
        for name in [i.name for i in self.rt.registry.alive() if i.name not in done]:
            if self.stopping:
                return  # the round is unfinished: its progress stays on disk for the next start
            self.step_matrix()
            inst = self.rt.registry.get(name)
            if inst is not None and inst.alive and not self.stopping:
                self.run_counted(name)
                done.add(name)
                self._save_round(done)
        if self.stopping and any(i.name not in done for i in self.rt.registry.alive()):
            return
        try:
            for b in process_requests(self.rt):
                log(f"born: {b.name} (parents: {', '.join(b.parents) or 'none'})")
        except Exception as e:
            log(f"births failed: {type(e).__name__}: {e}")
        try:
            promoted = canonize(self.cfg)
            for pid in promoted:
                log(f"canonized {pid}")
            for cid, name in apply_adopted_names(self.cfg, promoted):
                log(f"civilization {cid} is now named {name}")
                self._write_pages()
        except Exception as e:
            log(f"canonize failed: {type(e).__name__}: {e}")
        self.rt.registry.save()
        self._round_path.unlink(missing_ok=True)
        try:
            self._check_extinction()
        except Exception as e:
            log(f"extinction check failed: {type(e).__name__}: {e}")
        if self.publisher is not None:
            try:
                url = self.publisher.publish_round()
                if url:
                    log(f"website changes opened for review: {url}")
            except Exception as e:
                log(f"website publish failed: {type(e).__name__}: {e}")

    def idle(self, seconds: int) -> None:
        chunk = max(1, self.cfg.matrix_poll_seconds)
        waited = 0
        while waited < seconds and not self.stopping:
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
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, sched.handle_signal)
    while not sched.stopping:
        sched.run_round()
        if sched.stopping:
            break
        log(f"round complete; sleeping {cfg.heartbeat_interval}s")
        sched.idle(cfg.heartbeat_interval)
    log("stopped cleanly")


if __name__ == "__main__":
    main()
