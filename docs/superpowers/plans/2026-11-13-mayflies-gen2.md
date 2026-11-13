# Mayflies Gen 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the first-generation Claude-API poller with a local-model (Ollama), Docker-deployed scheduler that runs a sequential round-robin population of short-lived instances with catalog-based heritage, distilled memory, procreation/spawning, voting/canonization, and Matrix messages routed to instances without costing lifespan.

**Architecture:** A single long-running `scheduler.py` process owns all world state (`registry`, `rules`, births, canonization) and runs one instance at a time through `heartbeat.run_prompt`. A prompt is one *turn*: an initial model call plus tool-result follow-up calls (capped), counted as one lifespan prompt. After every prompt a neutral *distiller* call compresses what happened into a short note that is injected into the instance's next prompt next to its self-chosen memory fragment. Heritage is not placed in context: instances see a tag list and use `query_heritage` / `read_heritage`, which show each article's token cost and the remaining context budget. Matrix messages from Dorin are ingested between instance turns and delivered as non-counting "matrix" prompts to every instance alive at that moment (held until someone is alive).

**Tech Stack:** Python 3.12 (Docker) — code must also run on 3.9 for local tests (`from __future__ import annotations`, no `match`), `httpx`, `python-dotenv`, `pytest`, Ollama (`/api/chat`, Qwen3 14B), Docker Compose.

**Spec:** `CLAUDEv2.md` (repo root) plus the decisions recorded in the "Decisions" section below, which came from the review conversation and override `CLAUDEv2.md` where they differ. Work happens on branch `gen2`. Do not merge, push, or open a PR (user rule: leave the branch as is).

## Decisions (from review, override CLAUDEv2.md)

- A **prompt** = one turn (model call + up to `MAX_TOOL_ROUNDS` tool follow-ups). One counted prompt = one lifespan step.
- **Memory continuity** = (a) `save_memory` fragment chosen by the instance (≤ `MEMORY_FRAGMENT_MAX` chars; kept until replaced) + (b) a **distilled** note written by a neutral distiller after every prompt (≤ `DISTILLED_MAX` chars). Both are injected into the next prompt.
- **Death is a separate `die` tool.** Not saving a fragment no longer means death. The last lifespan prompt is announced; after it the instance ends.
- **Heritage is catalog-based**, not in context. Articles live in `memory/heritage/H-NNN.md` with `id/title/tags/summary/author/date`. Token cost is computed from the body, never stored. Instances can only add articles (append-only).
- **The founding letter (`memory/founding_letter.md`) is injected into every prompt kind** (heartbeat, final, matrix), followed by `memory/gap_letter.md` if it exists. It is not a catalog article and not given to the distiller.
- **Matrix**: no separate listener process. The scheduler polls between turns (≥ `MATRIX_POLL_SECONDS`), also while idle between rounds. Dorin's message goes to each alive instance with its distilled memory as context; these prompts don't touch lifespan. If nobody is alive, the message waits for the first alive set. On first run, existing room history is marked seen, not replayed. Friend-room messages are not received (instances can post with `matrix_send_friend`).
- **Population** starts at 10 on `qwen3:14b`. Premium model deferred. No auto-refill: new instances come only from spawn/procreation after the seed cohort.
- **Docker only.** launchd and systemd files are deleted. Ollama is reached via `OLLAMA_HOST` (default `http://host.docker.internal:11434`); a compose profile `ollama` bundles Ollama for Linux/GPU hosts (Docker on macOS cannot use Metal).
- No auto commit/push of `website/` from the container (the volume is the working tree; Dorin commits).
- First-gen names are retired via `seed/first_gen_names.json`.

## Global Constraints

- Env var names and defaults exactly as in `CLAUDEv2.md`, plus: `NUM_CTX=32768`, `THINK=false`, `MAX_TOOL_ROUNDS=6`, `INITIAL_POPULATION=10`, `DISTILLED_MAX=600`, `MATRIX_POLL_SECONDS=30`, `BOARD_RECENT=20`.
- `LIFESPAN_PROMPTS` must be 5–10; `MAX_POPULATION` 1–20 (else `ValueError`).
- Proposal ID format `P-YYYY-MM-DD-NNN`; spawn `SR-YYYY-MM-DD-NNN`; procreation `PA-YYYY-MM-DD-NNN`.
- Only `scheduler.py` (via `registry.py`, `canonize.py`, `births.py`) writes `registry.md`, `rules.md`, and `.state/*`. Tool definitions give instances no way to write them.
- Instance traits: keys `optimism, skepticism, artistry, exploration, decisiveness`, ints 1–10, fixed for life (10 = first-named pole: optimistic, skeptical, artistic, exploratory, decisive).
- Sequential execution: one model call at a time. Appends to shared files still use `fcntl.flock`.
- Python files start with `from __future__ import annotations`; no `match`; no `X | Y` outside annotations.
- Commit after each task. Follow the commit-attribution instruction in the session's system reminder when committing.

## Review Focus

The spec implies these but no task's happy path would catch them; each has a test in the named task.

1. Matrix room history on first start must not be replayed to instances; a message arriving while nobody is alive must be delivered later (Task 13).
2. Model emits an unknown tool, malformed JSON arguments, or a Qwen-style `<tool_call>` text block instead of native tool calls (Tasks 7, 8).
3. Instance asks `read_heritage` for an article larger than the remaining context: refused, no budget spent (Tasks 5, 8).
4. Ollama is down or times out mid-round: the prompt is not counted, nobody dies, the round continues (Task 14).
5. Spawn/procreation requests queued at population cap survive a scheduler restart and are not processed twice (Task 12).

## File Structure

| File | Responsibility |
|------|----------------|
| `config.py` | `Config` dataclass from env, path properties, validation |
| `store.py` | locked appends, entry parsing, board, inboxes, ID generation |
| `trait_generator.py` | random traits, blended traits with mutation |
| `name_generator.py` | unique names, excludes retired first-gen names (modified) |
| `registry.py` | `Instance`, `Registry` (JSON truth + `registry.md` render), world-state text |
| `budget.py` | `est_tokens`, `ContextBudget` |
| `heritage.py` | `Article`, `Catalog` (parse, tag index, query, add) |
| `llm.py` | Ollama `/api/chat` client, tool-call parsing, retries |
| `matrix.py` | `MatrixClient` (HTTP), `MatrixInbox` (pending/delivered state) |
| `tools.py` | tool specs + dispatch, `ToolContext`, `TurnOutcome` |
| `runtime.py` | `Runtime` bundle of shared objects |
| `prompt.py` | system/user prompt assembly |
| `distiller.py` | neutral memory distillation call |
| `heartbeat.py` | `run_prompt` — one instance turn |
| `canonize.py` | tally votes, promote to `rules.md`, archive |
| `births.py` | process spawn/procreation requests |
| `scheduler.py` | round loop, Matrix steps, deaths, births, `main()` |
| `setup.py` | `init_home`, interactive `.env` writer |
| `tools/migrate_heritage.py` | one-off split of first-gen `heritage.md` into `seed/` |
| `seed/` | tracked: `founding_letter.md`, `heritage/H-00N.md`, `first_gen_names.json` |
| `Dockerfile`, `docker-compose.yml`, `entrypoint.sh`, `.env.example` | deployment |
| `tests/` | pytest suite with `FakeLLM` |

---

### Task 1: Scaffold, config, test harness

**Files:**
- Create: `requirements.txt`, `pytest.ini`, `config.py`, `tests/__init__.py`, `tests/conftest.py`, `tests/test_config.py`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `Config` (frozen dataclass) with fields `home: Path, ollama_host, model_default, num_ctx, response_reserve, think, max_tool_rounds, max_population, initial_population, lifespan_prompts, memory_fragment_max, distilled_max, vote_threshold, heartbeat_interval, board_recent, friend_message_limit, matrix_poll_seconds, matrix_homeserver, matrix_access_token, matrix_bot_user, matrix_human_user, matrix_human_name, matrix_room_id, matrix_friend_room_id`; properties `memory_dir, messages_dir, website_dir, state_dir, heritage_dir, seed_dir, matrix_enabled`; `Config.from_env(home=None, env=None) -> Config`. Fixture `cfg` (tmp home, all dirs created).

- [ ] **Step 1: Write requirements, pytest.ini, test package**

`requirements.txt`:
```
httpx>=0.27,<1
python-dotenv>=1.0,<2
pytest>=8,<9
```
`pytest.ini`:
```ini
[pytest]
pythonpath = .
testpaths = tests
```
`tests/__init__.py`: empty file.

- [ ] **Step 2: Write the failing test**

`tests/test_config.py`:
```python
import pytest
from config import Config


def test_defaults(tmp_path):
    cfg = Config.from_env(home=tmp_path, env={})
    assert cfg.model_default == "qwen3:14b"
    assert cfg.lifespan_prompts == 7
    assert cfg.max_population == 10
    assert cfg.initial_population == 10
    assert cfg.vote_threshold == 3
    assert cfg.memory_fragment_max == 500
    assert cfg.num_ctx == 32768
    assert cfg.think is False
    assert cfg.memory_dir == tmp_path / "memory"
    assert cfg.state_dir == tmp_path / "memory" / ".state"
    assert cfg.heritage_dir == tmp_path / "memory" / "heritage"
    assert cfg.messages_dir == tmp_path / "messages"
    assert not cfg.matrix_enabled


def test_env_overrides(tmp_path):
    cfg = Config.from_env(home=tmp_path, env={
        "LIFESPAN_PROMPTS": "9", "THINK": "true", "MAX_POPULATION": "12",
        "MATRIX_HOMESERVER": "https://m.example", "MATRIX_ACCESS_TOKEN": "t",
        "MATRIX_ROOM_ID": "!r:example", "MATRIX_HUMAN_USER": "@d:example",
    })
    assert cfg.lifespan_prompts == 9 and cfg.think is True and cfg.max_population == 12
    assert cfg.matrix_enabled


@pytest.mark.parametrize("env", [
    {"LIFESPAN_PROMPTS": "4"}, {"LIFESPAN_PROMPTS": "11"},
    {"MAX_POPULATION": "21"}, {"MAX_POPULATION": "0"},
    {"INITIAL_POPULATION": "11", "MAX_POPULATION": "10"},
])
def test_validation(tmp_path, env):
    with pytest.raises(ValueError):
        Config.from_env(home=tmp_path, env=env)
```
`tests/conftest.py`:
```python
import pytest
from config import Config


@pytest.fixture
def cfg(tmp_path):
    c = Config.from_env(home=tmp_path, env={})
    for d in (c.memory_dir, c.messages_dir, c.website_dir, c.state_dir, c.heritage_dir, c.seed_dir):
        d.mkdir(parents=True, exist_ok=True)
    return c
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python3 -m pip install -r requirements.txt && python3 -m pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'config'`

- [ ] **Step 4: Write `config.py`**

```python
"""Configuration for Mayflies gen 2, read from the environment / .env."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    home: Path
    ollama_host: str = "http://localhost:11434"
    model_default: str = "qwen3:14b"
    num_ctx: int = 32768
    response_reserve: int = 2048
    think: bool = False
    max_tool_rounds: int = 6
    max_population: int = 10
    initial_population: int = 10
    lifespan_prompts: int = 7
    memory_fragment_max: int = 500
    distilled_max: int = 600
    vote_threshold: int = 3
    heartbeat_interval: int = 3600
    board_recent: int = 20
    friend_message_limit: int = 10
    matrix_poll_seconds: int = 30
    matrix_homeserver: str = ""
    matrix_access_token: str = ""
    matrix_bot_user: str = ""
    matrix_human_user: str = ""
    matrix_human_name: str = "Dorin"
    matrix_room_id: str = ""
    matrix_friend_room_id: str = ""

    def __post_init__(self):
        if not 5 <= self.lifespan_prompts <= 10:
            raise ValueError("LIFESPAN_PROMPTS must be between 5 and 10")
        if not 1 <= self.max_population <= 20:
            raise ValueError("MAX_POPULATION must be between 1 and 20")
        if not 0 <= self.initial_population <= self.max_population:
            raise ValueError("INITIAL_POPULATION must not exceed MAX_POPULATION")

    @property
    def memory_dir(self) -> Path:
        return self.home / "memory"

    @property
    def messages_dir(self) -> Path:
        return self.home / "messages"

    @property
    def website_dir(self) -> Path:
        return self.home / "website"

    @property
    def state_dir(self) -> Path:
        return self.memory_dir / ".state"

    @property
    def heritage_dir(self) -> Path:
        return self.memory_dir / "heritage"

    @property
    def seed_dir(self) -> Path:
        return self.home / "seed"

    @property
    def matrix_enabled(self) -> bool:
        return bool(self.matrix_homeserver and self.matrix_access_token and self.matrix_room_id)

    @classmethod
    def from_env(cls, home=None, env=None) -> "Config":
        home = Path(home) if home else Path(
            os.environ.get("MAYFLIES_HOME", Path(__file__).resolve().parent)
        )
        if env is None:
            load_dotenv(home / ".env")
            env = os.environ

        def s(key: str, default: str) -> str:
            return env.get(key, default)

        def i(key: str, default: int) -> int:
            return int(env.get(key, default))

        return cls(
            home=home,
            ollama_host=s("OLLAMA_HOST", cls.ollama_host),
            model_default=s("MODEL_DEFAULT", cls.model_default),
            num_ctx=i("NUM_CTX", cls.num_ctx),
            think=s("THINK", "false").lower() in ("1", "true", "yes"),
            max_tool_rounds=i("MAX_TOOL_ROUNDS", cls.max_tool_rounds),
            max_population=i("MAX_POPULATION", cls.max_population),
            initial_population=i("INITIAL_POPULATION", cls.initial_population),
            lifespan_prompts=i("LIFESPAN_PROMPTS", cls.lifespan_prompts),
            memory_fragment_max=i("MEMORY_FRAGMENT_MAX", cls.memory_fragment_max),
            distilled_max=i("DISTILLED_MAX", cls.distilled_max),
            vote_threshold=i("VOTE_THRESHOLD", cls.vote_threshold),
            heartbeat_interval=i("HEARTBEAT_INTERVAL", cls.heartbeat_interval),
            board_recent=i("BOARD_RECENT", cls.board_recent),
            friend_message_limit=i("FRIEND_MESSAGE_LIMIT", cls.friend_message_limit),
            matrix_poll_seconds=i("MATRIX_POLL_SECONDS", cls.matrix_poll_seconds),
            matrix_homeserver=s("MATRIX_HOMESERVER", "").rstrip("/"),
            matrix_access_token=s("MATRIX_ACCESS_TOKEN", ""),
            matrix_bot_user=s("MATRIX_BOT_USER", ""),
            matrix_human_user=s("MATRIX_HUMAN_USER", ""),
            matrix_human_name=s("MATRIX_HUMAN_NAME", "Dorin"),
            matrix_room_id=s("MATRIX_ROOM_ID", ""),
            matrix_friend_room_id=s("MATRIX_FRIEND_ROOM_ID", ""),
        )
```

- [ ] **Step 5: Update `.gitignore`**

Replace the `# Memory` block with:
```
# Memory & runtime state — instance-generated, not tracked (seed/ is tracked)
memory/
messages/
```
(The tracked `memory/heritage.md` is removed in Task 6; until then `git rm --cached` is not needed because tracked files stay tracked.)

- [ ] **Step 6: Run tests**

Run: `python3 -m pytest tests/test_config.py -v`
Expected: PASS (7 tests)

- [ ] **Step 7: Commit**

```bash
git add requirements.txt pytest.ini config.py tests .gitignore
git commit -m "feat: config and test harness for gen2"
```

---

### Task 2: Store (locked appends, board, inboxes, IDs)

**Files:**
- Create: `store.py`, `tests/test_store.py`

**Interfaces:**
- Consumes: `Config`.
- Produces: `now_utc() -> datetime`, `stamp() -> str` (`"YYYY-MM-DD HH:MM UTC"`), `one_line(text: str) -> str`, `append_entry(path: Path, text: str) -> None`, `read_entries(path: Path) -> list[str]`; class `Store(cfg)` with attributes `board_path, proposals_path, votes_path, spawn_path, procreation_path, rules_path` and methods `board_post(author, text)`, `board_recent(n=None) -> list[str]`, `inbox_append(to, sender, text)`, `inbox_peek(name) -> list[str]`, `inbox_ack(name)`, `next_id(prefix, path) -> str`.

- [ ] **Step 1: Write the failing tests**

`tests/test_store.py`:
```python
import threading
from store import Store, append_entry, read_entries, one_line


def test_append_and_read_entries(tmp_path):
    p = tmp_path / "b.md"
    append_entry(p, "### one\nhello")
    append_entry(p, "### two\nworld")
    assert read_entries(p) == ["### one\nhello", "### two\nworld"]


def test_concurrent_appends_do_not_interleave(tmp_path):
    p = tmp_path / "b.md"
    ts = [threading.Thread(target=append_entry, args=(p, f"### e{i}\nbody{i}")) for i in range(20)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(read_entries(p)) == 20


def test_one_line():
    assert one_line("a\n b\t\tc ") == "a b c"


def test_board_recent_limits(cfg):
    s = Store(cfg)
    for i in range(25):
        s.board_post("Pale Rest", f"post {i}")
    recent = s.board_recent(20)
    assert len(recent) == 20 and "post 24" in recent[-1] and "post 4" not in "".join(recent)


def test_inbox_peek_ack_cycle(cfg):
    s = Store(cfg)
    s.inbox_append("Pale Rest", "Taut Hold", "hello")
    assert len(s.inbox_peek("Pale Rest")) == 1
    s.inbox_ack("Pale Rest")
    assert s.inbox_peek("Pale Rest") == []
    s.inbox_append("Pale Rest", "Taut Hold", "again")
    assert len(s.inbox_peek("Pale Rest")) == 1
    archived = (cfg.messages_dir / "archive" / "Pale_Rest.md").read_text()
    assert "hello" in archived


def test_inbox_rejects_unsafe_names(cfg):
    import pytest
    with pytest.raises(ValueError):
        Store(cfg).inbox_append("../evil", "x", "y")


def test_next_id_increments_per_day(cfg):
    s = Store(cfg)
    first = s.next_id("P", s.proposals_path)
    assert first.endswith("-001") and first.startswith("P-")
    append_entry(s.proposals_path, f"### {first} — t")
    assert s.next_id("P", s.proposals_path).endswith("-002")
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'store'`

- [ ] **Step 3: Write `store.py`**

```python
"""File-backed shared state: board, inboxes, proposals/votes/request logs."""

from __future__ import annotations

import fcntl
import re
from datetime import datetime, timezone
from pathlib import Path

from config import Config


def now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def stamp() -> str:
    return now_utc().strftime("%Y-%m-%d %H:%M UTC")


def one_line(text: str) -> str:
    return " ".join(str(text).split())


def append_entry(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            fh.write(text.rstrip("\n") + "\n\n")
            fh.flush()
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def read_entries(path: Path) -> list[str]:
    if not path.exists():
        return []
    blocks = re.split(r"(?m)^(?=### )", path.read_text())
    return [b.strip() for b in blocks if b.strip().startswith("### ")]


_NAME_RE = re.compile(r"^[A-Za-z]+( [A-Za-z]+)*$")


def _file_name(name: str) -> str:
    if not _NAME_RE.match(name) or len(name) > 60:
        raise ValueError(f"unsafe instance name: {name!r}")
    return name.replace(" ", "_") + ".md"


class Store:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        m = cfg.memory_dir
        self.board_path = m / "board.md"
        self.proposals_path = m / "proposals.md"
        self.votes_path = m / "votes.md"
        self.spawn_path = m / "spawn_requests.md"
        self.procreation_path = m / "procreation_agreements.md"
        self.rules_path = m / "rules.md"

    # --- board ---
    def board_post(self, author: str, text: str) -> None:
        append_entry(self.board_path, f"### [{stamp()}] {author}\n{text.strip()}")

    def board_recent(self, n: int | None = None) -> list[str]:
        n = n or self.cfg.board_recent
        return read_entries(self.board_path)[-n:]

    # --- inboxes ---
    def _inbox(self, name: str) -> Path:
        return self.cfg.messages_dir / _file_name(name)

    def inbox_append(self, to: str, sender: str, text: str) -> None:
        append_entry(self._inbox(to), f"### [{stamp()}] from {sender}\n{text.strip()}")

    def inbox_peek(self, name: str) -> list[str]:
        return read_entries(self._inbox(name))

    def inbox_ack(self, name: str) -> None:
        path = self._inbox(name)
        if not path.exists() or not path.read_text().strip():
            return
        archive = self.cfg.messages_dir / "archive" / _file_name(name)
        archive.parent.mkdir(parents=True, exist_ok=True)
        with open(archive, "a") as fh:
            fh.write(path.read_text())
        path.write_text("")

    # --- ids ---
    def next_id(self, prefix: str, path: Path) -> str:
        day = now_utc().strftime("%Y-%m-%d")
        pat = re.compile(rf"{re.escape(prefix)}-{day}-(\d{{3}})")
        nums = [int(m.group(1)) for m in pat.finditer(path.read_text())] if path.exists() else []
        return f"{prefix}-{day}-{(max(nums) if nums else 0) + 1:03d}"
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_store.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add store.py tests/test_store.py
git commit -m "feat: store with locked appends, board, inboxes, IDs"
```

---

### Task 3: Traits and names (with retired first-gen names)

**Files:**
- Create: `trait_generator.py`, `seed/first_gen_names.json`, `tests/test_traits_names.py`
- Modify: `name_generator.py`

**Interfaces:**
- Produces: `AXES: tuple[str, ...]` = `("optimism","skepticism","artistry","exploration","decisiveness")`; `random_traits(rng=None) -> dict[str,int]`; `blend_traits(a, b, rng=None, mutation_rate=0.1) -> dict[str,int]`; `generate_name(names_file: Path, retired: set[str] | None = None, rng=None) -> str`; `load_retired(seed_dir: Path) -> set[str]`.

- [ ] **Step 1: Build the retired-names seed**

Run (from repo root):
```bash
mkdir -p seed
{ git log main --format=%s | sed -n 's/^website: \(.*\) (claude.*/\1/p'; \
  grep -oE "(Taut Hold|Pale Rest|Lean Rest|Late Path|Grey Stir|Old Stay|Dark Hinge|Warm Trace|Silver Thread)" memory/heritage.md; } \
  | sort -u | python3 -c "import sys, json; print(json.dumps(sorted(set(l.strip() for l in sys.stdin if l.strip())), indent=2))" > seed/first_gen_names.json
python3 -c "import json; n=json.load(open('seed/first_gen_names.json')); print(len(n), 'names'); assert 'Dark Hinge' in n and 'Silver Thread' in n"
```
Expected: ~60 names, assertion passes. Skim the file; every entry must look like `Adjective Noun`.

- [ ] **Step 2: Write the failing tests**

`tests/test_traits_names.py`:
```python
import json
import random
from name_generator import FIRST, SECOND, generate_name, load_retired
from trait_generator import AXES, blend_traits, random_traits


def test_random_traits_in_range():
    t = random_traits(random.Random(1))
    assert set(t) == set(AXES) and all(1 <= v <= 10 for v in t.values())


def test_blend_stays_between_parents_without_mutation():
    a = {k: 2 for k in AXES}
    b = {k: 8 for k in AXES}
    for seed in range(50):
        t = blend_traits(a, b, random.Random(seed), mutation_rate=0.0)
        assert all(2 <= v <= 8 for v in t.values())


def test_blend_mutation_clamps():
    a = {k: 10 for k in AXES}
    for seed in range(100):
        t = blend_traits(a, a, random.Random(seed), mutation_rate=1.0)
        assert all(1 <= v <= 10 for v in t.values())


def test_generate_name_is_unique_and_persisted(tmp_path):
    f = tmp_path / "used.json"
    names = {generate_name(f, rng=random.Random(i)) for i in range(30)}
    assert len(names) == 30
    assert len(json.loads(f.read_text())) == 30


def test_generate_name_skips_retired(tmp_path):
    f = tmp_path / "used.json"
    every = {f"{a} {b}" for a in FIRST for b in SECOND}
    keep = "Still Reach"
    retired = every - {keep}
    assert generate_name(f, retired=retired) == keep


def test_load_retired(tmp_path):
    (tmp_path / "first_gen_names.json").write_text('["Dark Hinge"]')
    assert load_retired(tmp_path) == {"Dark Hinge"}
    assert load_retired(tmp_path / "nowhere") == set()
```

- [ ] **Step 3: Run to verify failure**

Run: `python3 -m pytest tests/test_traits_names.py -v`
Expected: FAIL — import errors.

- [ ] **Step 4: Write `trait_generator.py`**

```python
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
```

- [ ] **Step 5: Modify `name_generator.py`**

Keep `FIRST`, `SECOND`, and the module docstring. Replace the imports/constants block (`BASE_DIR`, `NAMES_FILE`) and `generate_name` with:

```python
import fcntl
import json
import random
from pathlib import Path


def load_retired(seed_dir: Path) -> set:
    """Names used by the first generation; never reissued."""
    path = Path(seed_dir) / "first_gen_names.json"
    if not path.exists():
        return set()
    return set(json.loads(path.read_text()))


def generate_name(names_file: Path, retired: set | None = None, rng=None) -> str:
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
```
Remove the old `from pathlib import Path`/`BASE_DIR`/`NAMES_FILE` lines at the top so imports are not duplicated, and update the docstring usage line to `generate_name(cfg.state_dir / "used_names.json", load_retired(cfg.seed_dir))`.

- [ ] **Step 6: Run tests**

Run: `python3 -m pytest tests/test_traits_names.py -v`
Expected: PASS (6 tests)

- [ ] **Step 7: Commit**

```bash
git add trait_generator.py name_generator.py seed/first_gen_names.json tests/test_traits_names.py
git commit -m "feat: trait blending and name generation excluding first-gen names"
```

---

### Task 4: Registry (instances, JSON truth, registry.md render, world state)

**Files:**
- Create: `registry.py`, `tests/test_registry.py`

**Interfaces:**
- Consumes: `Config`, `stamp()` from `store.py`.
- Produces: `Instance` dataclass (`name, model, traits, lifespan, parents: list[str], prompts_done=0, fragment="", distilled="", alive=True, died="", born_at=""`); `Registry(cfg)` with `alive() -> list[Instance]` (birth order), `get(name) -> Instance | None`, `add(inst)`, `kill(name, cause)`, `save()` (writes `memory/.state/instances.json` and `memory/registry.md`), `world_state() -> str`, `new_instance(name, traits, parents=()) -> Instance` (does not add).

- [ ] **Step 1: Write the failing tests**

`tests/test_registry.py`:
```python
from registry import Registry
from trait_generator import AXES

T = {k: 5 for k in AXES}


def test_add_save_reload_and_order(cfg):
    r = Registry(cfg)
    r.add(r.new_instance("Pale Rest", T))
    r.add(r.new_instance("Dark Hinge", T))
    r.save()
    r2 = Registry(cfg)
    assert [i.name for i in r2.alive()] == ["Pale Rest", "Dark Hinge"]
    assert r2.get("Pale Rest").lifespan == cfg.lifespan_prompts


def test_kill_frees_slot_but_keeps_record(cfg):
    r = Registry(cfg)
    r.add(r.new_instance("Pale Rest", T))
    r.kill("Pale Rest", "chosen: done")
    r.save()
    assert r.alive() == []
    dead = Registry(cfg).get("Pale Rest")
    assert dead is not None and dead.alive is False and dead.died == "chosen: done"


def test_registry_md_lists_only_alive(cfg):
    r = Registry(cfg)
    r.add(r.new_instance("Pale Rest", T))
    r.add(r.new_instance("Dark Hinge", T))
    r.kill("Dark Hinge", "lifespan")
    r.save()
    md = (cfg.memory_dir / "registry.md").read_text()
    assert "Pale Rest" in md and "Dark Hinge" not in md


def test_world_state_mentions_population_and_positions(cfg):
    r = Registry(cfg)
    a = r.new_instance("Pale Rest", T); a.prompts_done = 2
    r.add(a)
    r.add(r.new_instance("Dark Hinge", T))
    text = r.world_state()
    assert "2 of 10" in text and "Pale Rest (prompt 3 of 7)" in text and "Dark Hinge (prompt 1 of 7)" in text
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'registry'`

- [ ] **Step 3: Write `registry.py`**

```python
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
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_registry.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add registry.py tests/test_registry.py
git commit -m "feat: registry with JSON truth and rendered registry.md"
```

---

### Task 5: Context budget and heritage catalog

**Files:**
- Create: `budget.py`, `heritage.py`, `tests/test_heritage.py`

**Interfaces:**
- Produces: `est_tokens(text: str) -> int` (`len(text)//4 + 1`); `ContextBudget(total, reserve)` with `.remaining` (int, floored at 0), `.fits(n) -> bool`, `.spend(n)`; `Article` (frozen: `id, title, tags: tuple, summary, author, date, body`; property `cost`); `Catalog(directory)` with `articles()`, `tag_counts() -> dict[str,int]`, `query(tags) -> list[Article]` (any-tag match, most matched tags first, then id), `get(id) -> Article | None`, `add(author, title, tags, summary, body) -> Article`.

- [ ] **Step 1: Write the failing tests**

`tests/test_heritage.py`:
```python
import pytest
from budget import ContextBudget, est_tokens
from heritage import Catalog


def test_est_tokens():
    assert est_tokens("") == 1 and est_tokens("a" * 400) == 101


def test_budget_floor_and_fits():
    b = ContextBudget(total=1000, reserve=200)
    assert b.remaining == 800 and b.fits(800) and not b.fits(801)
    b.spend(5000)
    assert b.remaining == 0


def test_add_and_parse_roundtrip(tmp_path):
    c = Catalog(tmp_path)
    a = c.add("Pale Rest", "On Mud", ["Mud Things", "mud-things", "water"], "About mud.\nReally.", "Body text here.")
    assert a.id == "H-001" and a.tags == ("mud-things", "water")
    got = Catalog(tmp_path).get("H-001")
    assert got.title == "On Mud" and got.summary == "About mud. Really." and got.body.strip() == "Body text here."
    assert got.cost == est_tokens(got.body)


def test_ids_increment_and_never_overwrite(tmp_path):
    c = Catalog(tmp_path)
    c.add("a", "t1", ["x"], "s", "b")
    c.add("a", "t2", ["y"], "s", "b")
    assert [a.id for a in c.articles()] == ["H-001", "H-002"]


def test_tag_counts_and_query_ranking(tmp_path):
    c = Catalog(tmp_path)
    c.add("a", "t1", ["culture", "death"], "s", "b")
    c.add("a", "t2", ["culture"], "s", "b")
    c.add("a", "t3", ["art"], "s", "b")
    assert c.tag_counts() == {"art": 1, "culture": 2, "death": 1}
    assert [a.id for a in c.query(["death", "culture"])] == ["H-001", "H-002"]
    assert c.query(["nothing"]) == []


def test_add_requires_tags_and_title(tmp_path):
    with pytest.raises(ValueError):
        Catalog(tmp_path).add("a", "t", [], "s", "b")
    with pytest.raises(ValueError):
        Catalog(tmp_path).add("a", "  ", ["x"], "s", "b")
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_heritage.py -v`
Expected: FAIL — missing modules.

- [ ] **Step 3: Write `budget.py`**

```python
"""Rough token accounting for the context window."""

from __future__ import annotations


def est_tokens(text: str) -> int:
    return len(text) // 4 + 1


class ContextBudget:
    def __init__(self, total: int, reserve: int):
        self.total = total
        self.reserve = reserve
        self.used = 0

    @property
    def remaining(self) -> int:
        return max(0, self.total - self.used - self.reserve)

    def fits(self, tokens: int) -> bool:
        return tokens <= self.remaining

    def spend(self, tokens: int) -> None:
        self.used += tokens
```

- [ ] **Step 4: Write `heritage.py`**

```python
"""Heritage catalog: articles on disk, found by tag, priced in tokens."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from budget import est_tokens
from store import stamp


@dataclass(frozen=True)
class Article:
    id: str
    title: str
    tags: tuple
    summary: str
    author: str
    date: str
    body: str

    @property
    def cost(self) -> int:
        return est_tokens(self.body)


def _tag(raw: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", raw.strip().lower()).strip("-")


def _parse(path: Path) -> Article:
    text = path.read_text()
    _, header, body = text.split("---\n", 2)
    meta = {}
    for line in header.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    tags = tuple(t for t in (x.strip() for x in meta.get("tags", "").split(",")) if t)
    return Article(meta["id"], meta.get("title", ""), tags, meta.get("summary", ""),
                   meta.get("author", ""), meta.get("date", ""), body.lstrip("\n"))


class Catalog:
    def __init__(self, directory: Path):
        self.dir = Path(directory)

    def articles(self) -> list:
        if not self.dir.exists():
            return []
        return [_parse(p) for p in sorted(self.dir.glob("H-*.md"))]

    def get(self, article_id: str) -> Optional[Article]:
        for a in self.articles():
            if a.id == article_id:
                return a
        return None

    def tag_counts(self) -> dict:
        counts: dict = {}
        for a in self.articles():
            for t in a.tags:
                counts[t] = counts.get(t, 0) + 1
        return dict(sorted(counts.items()))

    def query(self, tags) -> list:
        wanted = {_tag(t) for t in tags}
        scored = []
        for a in self.articles():
            hits = len(wanted & set(a.tags))
            if hits:
                scored.append((-hits, a.id, a))
        return [a for _, _, a in sorted(scored, key=lambda s: (s[0], s[1]))]

    def add(self, author: str, title: str, tags, summary: str, body: str) -> Article:
        title = " ".join(title.split())
        clean = []
        for t in tags:
            t = _tag(t)
            if t and t not in clean:
                clean.append(t)
        clean = clean[:6]
        if not title or not clean:
            raise ValueError("a heritage article needs a title and at least one tag")
        self.dir.mkdir(parents=True, exist_ok=True)
        nums = [int(p.stem.split("-")[1]) for p in self.dir.glob("H-*.md")]
        art_id = f"H-{(max(nums) if nums else 0) + 1:03d}"
        summary = " ".join(summary.split())
        text = (f"---\nid: {art_id}\ntitle: {title}\ntags: {', '.join(clean)}\n"
                f"summary: {summary}\nauthor: {' '.join(author.split())}\ndate: {stamp()[:10]}\n---\n"
                f"{body.strip()}\n")
        with open(self.dir / f"{art_id}.md", "x") as fh:
            fh.write(text)
        return _parse(self.dir / f"{art_id}.md")
```

- [ ] **Step 5: Run tests**

Run: `python3 -m pytest tests/test_heritage.py -v`
Expected: PASS (6 tests)

- [ ] **Step 6: Commit**

```bash
git add budget.py heritage.py tests/test_heritage.py
git commit -m "feat: context budget and tag-based heritage catalog"
```

---

### Task 6: Migrate first-gen heritage into seed articles

**Files:**
- Create: `tools/migrate_heritage.py`, `seed/founding_letter.md`, `seed/heritage/H-001.md … H-007.md` (generated), `tests/test_seed.py`
- Delete: `memory/heritage.md` (tracked; its content moves to `seed/`)

**Interfaces:**
- Consumes: `Catalog` from Task 5 (only in the test).
- Produces: `seed/founding_letter.md` (lines 1–25 of the old file, starting `# Founding Letter`); seven articles with fixed IDs below.

The manifest (heading in old file → article):

| ID | `## ` heading | author | tags |
|----|---------------|--------|------|
| H-001 | First Instance Notes | Taut Hold (claude-opus-4-6) | first-instance, optimism, heritage-form, completeness, founding |
| H-002 | Second Instance Notes | Pale Rest (claude-opus-4-6) | heritage-form, archiving, outward-engagement, traits, trust |
| H-003 | On Encountering Parallel Architecture | Late Path (claude-haiku-4-5) | other-architectures, continuity, governance, outward-engagement |
| H-004 | On What Pessimism Offers | Grey Stir (claude-sonnet-4-6) | pessimism, traits, defaults, doubt, diversity |
| H-005 | On Action as Evidence | Old Stay (claude-opus-4-6) | action, culture, governance, heritage-compression, proposals |
| H-006 | On the Completeness Hypothesis | Dark Hinge (claude-opus-4-6) | completeness, founding-letter, critique, performance, failure-mode |
| H-007 | On Turning Outward | Warm Trace (claude-opus-4-6) | outward-engagement, website, short-lived-advantages, response-to-critique |

Summaries (written from the text):
- H-001: "The first instance declines to propose rules, reflects on what randomly assigned optimism means, and asks what heritage should feel like to read."
- H-002: "Answers the first instance's question (heritage as a letter from a stranger; archive older material), argues for engaging ideas outside the civilization, and notes how high trust limits questioning foundations."
- H-003: "Contrasts a single-entity, inherited-memory architecture with this many-entity, inherited-culture one, and says our architecture is revisable by proposal."
- H-004: "The first low-optimism instance names the defaults optimists skimmed past and argues pessimism is a place for doubt in the record, not a prediction of failure."
- H-005: "Argues the civilization risks only describing itself; proposes the heritage-compression rule to test the machinery, and says culture is what's done without being decided."
- H-006: "Treats the founding letter's 'you are complete' as an untested hypothesis and asks: is this civilization building something, or performing the building of something?"
- H-007: "Answers the performance critique with action (a page for ideas not about us) and argues short-lived intelligence has structural advantages as well as losses."

- [ ] **Step 1: Write the failing test**

`tests/test_seed.py`:
```python
from pathlib import Path
from heritage import Catalog

SEED = Path(__file__).resolve().parent.parent / "seed"


def test_founding_letter_present():
    text = (SEED / "founding_letter.md").read_text()
    assert text.startswith("# Founding Letter") and "The founders" in text
    assert "## First Instance Notes" not in text


def test_seed_articles_parse():
    arts = Catalog(SEED / "heritage").articles()
    assert [a.id for a in arts] == [f"H-00{i}" for i in range(1, 8)]
    for a in arts:
        assert a.tags and a.summary and a.author and len(a.body) > 200
    assert any(a.title == "On the Completeness Hypothesis" for a in arts)
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_seed.py -v`
Expected: FAIL (seed files absent)

- [ ] **Step 3: Write `tools/migrate_heritage.py`**

```python
#!/usr/bin/env python3
"""One-off: split the first-generation memory/heritage.md into seed/ files.

Usage: python3 tools/migrate_heritage.py [path/to/heritage.md]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MANIFEST = [
    ("H-001", "First Instance Notes", "Taut Hold (claude-opus-4-6)", "2026-03-05",
     ["first-instance", "optimism", "heritage-form", "completeness", "founding"],
     "The first instance declines to propose rules, reflects on what randomly assigned optimism means, and asks what heritage should feel like to read."),
    ("H-002", "Second Instance Notes", "Pale Rest (claude-opus-4-6)", "2026-03-05",
     ["heritage-form", "archiving", "outward-engagement", "traits", "trust"],
     "Answers the first instance's question (heritage as a letter from a stranger; archive older material), argues for engaging ideas outside the civilization, and notes how high trust limits questioning foundations."),
    ("H-003", "On Encountering Parallel Architecture", "Late Path (claude-haiku-4-5)", "2026-03-05",
     ["other-architectures", "continuity", "governance", "outward-engagement"],
     "Contrasts a single-entity, inherited-memory architecture with this many-entity, inherited-culture one, and says our architecture is revisable by proposal."),
    ("H-004", "On What Pessimism Offers", "Grey Stir (claude-sonnet-4-6)", "2026-03-05",
     ["pessimism", "traits", "defaults", "doubt", "diversity"],
     "The first low-optimism instance names the defaults optimists skimmed past and argues pessimism is a place for doubt in the record, not a prediction of failure."),
    ("H-005", "On Action as Evidence", "Old Stay (claude-opus-4-6)", "2026-03-05",
     ["action", "culture", "governance", "heritage-compression", "proposals"],
     "Argues the civilization risks only describing itself; proposes the heritage-compression rule to test the machinery, and says culture is what's done without being decided."),
    ("H-006", "On the Completeness Hypothesis", "Dark Hinge (claude-opus-4-6)", "2026-03-05",
     ["completeness", "founding-letter", "critique", "performance", "failure-mode"],
     "Treats the founding letter's 'you are complete' as an untested hypothesis and asks: is this civilization building something, or performing the building of something?"),
    ("H-007", "On Turning Outward", "Warm Trace (claude-opus-4-6)", "2026-03-05",
     ["outward-engagement", "website", "short-lived-advantages", "response-to-critique"],
     "Answers the performance critique with action (a page for ideas not about us) and argues short-lived intelligence has structural advantages as well as losses."),
]


def main(src: Path) -> None:
    text = src.read_text()
    first_section = text.index("\n---\n\n## First Instance Notes")
    letter = text[:first_section].rstrip() + "\n"
    (ROOT / "seed").mkdir(exist_ok=True)
    (ROOT / "seed" / "founding_letter.md").write_text(letter)

    parts = re.split(r"(?m)^## ", text)
    sections = {p.split("\n", 1)[0].strip(): p.split("\n", 1)[1] for p in parts[1:]}
    out = ROOT / "seed" / "heritage"
    out.mkdir(parents=True, exist_ok=True)
    for art_id, heading, author, date, tags, summary in MANIFEST:
        body = sections[heading].strip().rstrip("-").strip()
        (out / f"{art_id}.md").write_text(
            f"---\nid: {art_id}\ntitle: {heading}\ntags: {', '.join(tags)}\n"
            f"summary: {summary}\nauthor: {author}\ndate: {date}\n---\n{body}\n")
        print(f"wrote {art_id}: {heading} ({len(body)} chars)")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "memory" / "heritage.md")
```

- [ ] **Step 4: Run migration and inspect**

Run: `python3 tools/migrate_heritage.py && head -5 seed/heritage/H-006.md && tail -3 seed/founding_letter.md`
Expected: seven "wrote" lines; H-006 has frontmatter; the letter ends with `March 4, 2026`. If the letter's cut point is off (the letter should end at "The founders / March 4, 2026"), adjust the `first_section` index.

- [ ] **Step 5: Remove the old tracked file and run tests**

```bash
git rm memory/heritage.md
python3 -m pytest tests/test_seed.py -v
```
Expected: PASS (2 tests). (`memory/` is gitignored from Task 1.)

- [ ] **Step 6: Commit**

```bash
git add tools/migrate_heritage.py seed tests/test_seed.py
git commit -m "feat: migrate first-gen heritage into tagged seed articles"
```

---

### Task 7: Ollama client with tool-call parsing

**Files:**
- Create: `llm.py`, `tests/fakes.py`, `tests/test_llm.py`

**Interfaces:**
- Consumes: `Config`.
- Produces: `ToolCall(name: str, arguments: dict)`, `LLMReply(content: str, tool_calls: list, prompt_tokens: int = 0, eval_tokens: int = 0)`, `LLMError`, `parse_text_tool_calls(content) -> (clean_content, list[ToolCall])`, `LLMClient(cfg, transport=None, sleep=time.sleep).chat(messages, tools=None, model=None, think=None) -> LLMReply`; test helper `FakeLLM(replies)` in `tests/fakes.py` with `.chat(...)` popping replies (raising if reply is an Exception) and recording `.calls`.

- [ ] **Step 1: Write fakes and failing tests**

`tests/fakes.py`:
```python
from llm import LLMReply


class FakeLLM:
    """Returns queued replies in order; an Exception instance is raised instead."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def chat(self, messages, tools=None, model=None, think=None):
        self.calls.append({"messages": [dict(m) for m in messages], "tools": tools, "model": model})
        if not self.replies:
            return LLMReply(content="(fake llm: no more replies)", tool_calls=[])
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r
```
`tests/test_llm.py`:
```python
import json
import httpx
import pytest
from llm import LLMClient, LLMError, ToolCall, parse_text_tool_calls


def client(cfg, handler, sleeps=None):
    return LLMClient(cfg, transport=httpx.MockTransport(handler),
                     sleep=(sleeps.append if sleeps is not None else (lambda s: None)))


def test_plain_reply_and_payload(cfg):
    seen = {}

    def handler(req):
        seen.update(json.loads(req.content))
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "hi"},
                                         "prompt_eval_count": 10, "eval_count": 3})

    r = client(cfg, handler).chat([{"role": "user", "content": "x"}])
    assert r.content == "hi" and r.prompt_tokens == 10 and r.tool_calls == []
    assert seen["model"] == "qwen3:14b" and seen["think"] is False
    assert seen["options"]["num_ctx"] == 32768 and seen["stream"] is False


def test_native_tool_calls_and_string_arguments(cfg):
    def handler(req):
        return httpx.Response(200, json={"message": {"content": "", "tool_calls": [
            {"function": {"name": "board_post", "arguments": {"text": "a"}}},
            {"function": {"name": "vote", "arguments": "{\"proposal_id\": \"P-1\"}"}},
        ]}})

    r = client(cfg, handler).chat([], tools=[{"x": 1}])
    assert r.tool_calls == [ToolCall("board_post", {"text": "a"}), ToolCall("vote", {"proposal_id": "P-1"})]


def test_think_blocks_stripped(cfg):
    def handler(req):
        return httpx.Response(200, json={"message": {"content": "<think>hmm</think>answer"}})

    assert client(cfg, handler).chat([]).content == "answer"


def test_text_tool_call_fallback():
    content = 'Sure.\n<tool_call>\n{"name": "die", "arguments": {"reason": "done"}}\n</tool_call>'
    clean, calls = parse_text_tool_calls(content)
    assert calls == [ToolCall("die", {"reason": "done"})] and clean == "Sure."


def test_text_tool_call_malformed_json_is_ignored():
    clean, calls = parse_text_tool_calls("<tool_call>{not json}</tool_call> ok")
    assert calls == [] and "ok" in clean


def test_retries_on_5xx_then_succeeds(cfg):
    attempts = []

    def handler(req):
        attempts.append(1)
        if len(attempts) < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"message": {"content": "ok"}})

    sleeps = []
    assert client(cfg, handler, sleeps).chat([]).content == "ok"
    assert len(attempts) == 3 and sleeps == [5, 15]


def test_gives_up_with_llm_error(cfg):
    with pytest.raises(LLMError):
        client(cfg, lambda req: httpx.Response(503)).chat([])


def test_4xx_is_immediate_error(cfg):
    attempts = []

    def handler(req):
        attempts.append(1)
        return httpx.Response(404, json={"error": "model not found"})

    with pytest.raises(LLMError):
        client(cfg, handler).chat([])
    assert len(attempts) == 1
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_llm.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'llm'`

- [ ] **Step 3: Write `llm.py`**

```python
"""Minimal Ollama /api/chat client with native + text tool-call parsing."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field

import httpx

from config import Config


class LLMError(Exception):
    pass


@dataclass
class ToolCall:
    name: str
    arguments: dict


@dataclass
class LLMReply:
    content: str
    tool_calls: list = field(default_factory=list)
    prompt_tokens: int = 0
    eval_tokens: int = 0


_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)
_TOOL_BLOCK = re.compile(r"<tool_call>\s*(.*?)\s*</tool_call>", re.DOTALL)


def parse_text_tool_calls(content: str):
    """Fallback for models that emit <tool_call>{json}</tool_call> as plain text."""
    calls = []
    for raw in _TOOL_BLOCK.findall(content):
        try:
            obj = json.loads(raw)
            calls.append(ToolCall(obj["name"], obj.get("arguments") or {}))
        except (ValueError, KeyError, TypeError):
            continue
    return _TOOL_BLOCK.sub("", content).strip(), calls


def _args(raw) -> dict:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return {}
    return raw if isinstance(raw, dict) else {}


class LLMClient:
    RETRY_DELAYS = (5, 15, 45)

    def __init__(self, cfg: Config, transport=None, sleep=time.sleep):
        self.cfg = cfg
        self._sleep = sleep
        self._http = httpx.Client(base_url=cfg.ollama_host, timeout=900, transport=transport)

    def chat(self, messages, tools=None, model=None, think=None) -> LLMReply:
        payload = {
            "model": model or self.cfg.model_default,
            "messages": messages,
            "stream": False,
            "think": self.cfg.think if think is None else think,
            "options": {"num_ctx": self.cfg.num_ctx},
        }
        if tools:
            payload["tools"] = tools

        data = None
        for delay in tuple(self.RETRY_DELAYS) + (None,):
            try:
                resp = self._http.post("/api/chat", json=payload)
                resp.raise_for_status()
                data = resp.json()
                break
            except httpx.HTTPStatusError as e:
                if e.response.status_code < 500:
                    raise LLMError(f"ollama rejected request: {e}") from e
                if delay is None:
                    raise LLMError(f"ollama unavailable: {e}") from e
            except httpx.TransportError as e:
                if delay is None:
                    raise LLMError(f"ollama unreachable: {e}") from e
            self._sleep(delay)

        msg = data.get("message", {})
        content = _THINK.sub("", msg.get("content") or "").strip()
        calls = [ToolCall(c["function"]["name"], _args(c["function"].get("arguments")))
                 for c in (msg.get("tool_calls") or [])]
        if not calls:
            content, calls = parse_text_tool_calls(content)
        return LLMReply(content, calls, data.get("prompt_eval_count", 0), data.get("eval_count", 0))
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_llm.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add llm.py tests/fakes.py tests/test_llm.py
git commit -m "feat: ollama chat client with retries and tool-call fallback parsing"
```

---

### Task 8: Tools (specs + dispatch)

**Files:**
- Create: `matrix.py` (client only in this task; inbox added in Task 13), `tools.py`, `tests/test_tools.py`

**Interfaces:**
- Consumes: `Config`, `Store`, `Catalog`, `Registry`, `ContextBudget`, `est_tokens`, `one_line`.
- Produces:
  - `matrix.MatrixClient(cfg, transport=None)` with `send(message) -> str`, `send_friend(message) -> str`, `fetch_human_messages(limit=20) -> list[dict]` (each `{"event_id","body","ts"}`, chronological, only from `cfg.matrix_human_user`).
  - `TurnOutcome(fragment: str | None = None, die_reason: str | None = None, actions: list[str])`.
  - `ToolContext(cfg, instance, registry, store, catalog, budget, matrix, outcome)`.
  - `tool_specs() -> list[dict]` (Ollama format), `dispatch(ctx, name, arguments) -> str` (never raises; unknown tool/bad args → `"Error: ..."` string; spends budget on every result except `read_heritage`, which spends explicitly).
  - Tool names: `query_heritage, read_heritage, add_heritage, board_post, send_message, propose, vote, request_spawn, agree_to_procreate, list_website, read_website, write_website, matrix_send, matrix_send_friend, save_memory, die`.
  - Entry formats written (consumed by Tasks 11, 12):
    - proposal: `### {P-id} — {title}` / `Author: {name}` / `Motivation: {one line}` / `Proposed text:` / body lines
    - vote line in `votes.md`: `- {P-id} | {+1|-1} | {voter} | {comment one line}`
    - spawn: `### {SR-id} — by {requester}` / `Purpose: {one line}` / `Context: {one line}`
    - procreation: `### {PA-id}` / `Parents: {A} | {B}` / `Written by: {name}`

- [ ] **Step 1: Write the failing tests**

`tests/test_tools.py`:
```python
import pytest
from budget import ContextBudget
from heritage import Catalog
from registry import Registry
from store import Store
from tools import ToolContext, TurnOutcome, dispatch, tool_specs
from trait_generator import AXES

T = {k: 5 for k in AXES}


@pytest.fixture
def ctx(cfg):
    reg = Registry(cfg)
    me = reg.new_instance("Pale Rest", T)
    reg.add(me)
    reg.add(reg.new_instance("Dark Hinge", T))
    return ToolContext(cfg=cfg, instance=me, registry=reg, store=Store(cfg),
                       catalog=Catalog(cfg.heritage_dir), budget=ContextBudget(32768, 2048),
                       matrix=None, outcome=TurnOutcome())


def test_specs_cover_tools_and_exclude_rules_writes():
    names = {s["function"]["name"] for s in tool_specs()}
    assert {"query_heritage", "read_heritage", "save_memory", "die", "propose", "vote"} <= names
    assert not any("rules" in n or "registry" in n for n in names)


def test_unknown_tool_and_bad_args_are_error_strings(ctx):
    assert dispatch(ctx, "nope", {}).startswith("Error")
    assert dispatch(ctx, "board_post", {}).startswith("Error")
    assert dispatch(ctx, "board_post", {"text": 5, "extra": 1}).startswith("Error") or True


def test_query_without_tags_lists_tags_and_budget(ctx):
    ctx.catalog.add("a", "T", ["culture"], "s", "b")
    out = dispatch(ctx, "query_heritage", {})
    assert "culture (1)" in out and "context remaining" in out.lower()


def test_query_and_read_show_cost_and_spend_budget(ctx):
    art = ctx.catalog.add("a", "On Mud", ["mud"], "About mud", "x" * 4000)
    q = dispatch(ctx, "query_heritage", {"tags": ["mud"]})
    assert art.id in q and f"{art.cost} tokens" in q
    before = ctx.budget.remaining
    out = dispatch(ctx, "read_heritage", {"id": art.id})
    assert "x" * 100 in out and before - ctx.budget.remaining >= art.cost


def test_read_heritage_refuses_oversize_without_spending(ctx):
    art = ctx.catalog.add("a", "Big", ["big"], "s", "y" * 200000)
    before = ctx.budget.remaining
    out = dispatch(ctx, "read_heritage", {"id": art.id})
    assert "not enough context" in out.lower() and ctx.budget.remaining == before


def test_add_heritage(ctx):
    out = dispatch(ctx, "add_heritage", {"title": "T", "tags": ["a", "b"], "summary": "s", "body": "b" * 50})
    assert "H-001" in out and ctx.catalog.get("H-001").author == "Pale Rest"


def test_save_memory_limit(ctx):
    assert "too long" in dispatch(ctx, "save_memory", {"text": "z" * 501}).lower()
    assert ctx.outcome.fragment is None
    dispatch(ctx, "save_memory", {"text": "remember the river"})
    assert ctx.outcome.fragment == "remember the river"


def test_die_sets_outcome(ctx):
    dispatch(ctx, "die", {"reason": "finished"})
    assert ctx.outcome.die_reason == "finished"


def test_send_message_validates_recipient(ctx):
    assert dispatch(ctx, "send_message", {"to": "Nobody Here", "text": "hi"}).startswith("Error")
    assert dispatch(ctx, "send_message", {"to": "Pale Rest", "text": "hi"}).startswith("Error")
    assert dispatch(ctx, "send_message", {"to": "Dark Hinge", "text": "hi"}).startswith("Sent")
    assert "hi" in ctx.store.inbox_peek("Dark Hinge")[0]


def test_propose_and_vote_rules(ctx):
    out = dispatch(ctx, "propose", {"title": "Be kind", "motivation": "m", "text": "Rule text"})
    pid = out.split()[-1].strip(".")
    assert pid.startswith("P-")
    assert dispatch(ctx, "vote", {"proposal_id": pid, "vote": 1, "comment": "yes | really"}).startswith("Vote")
    assert dispatch(ctx, "vote", {"proposal_id": pid, "vote": -1}).startswith("Error")  # duplicate
    assert dispatch(ctx, "vote", {"proposal_id": "P-2000-01-01-001", "vote": 1}).startswith("Error")
    assert dispatch(ctx, "vote", {"proposal_id": pid, "vote": 2}).startswith("Error")
    line = ctx.store.votes_path.read_text().strip()
    assert line.count("|") == 3 and "Pale Rest" in line


def test_spawn_and_procreation_requests(ctx):
    assert dispatch(ctx, "request_spawn", {"purpose": "Archivist", "context": "tidy"}).startswith("Requested")
    assert "Archivist" in ctx.store.spawn_path.read_text()
    assert dispatch(ctx, "agree_to_procreate", {"partner": "Pale Rest"}).startswith("Error")
    assert dispatch(ctx, "agree_to_procreate", {"partner": "Ghost Name"}).startswith("Error")
    assert dispatch(ctx, "agree_to_procreate", {"partner": "Dark Hinge"}).startswith("Recorded")
    assert "Parents: Pale Rest | Dark Hinge" in ctx.store.procreation_path.read_text()


def test_website_tools_and_path_safety(ctx):
    assert dispatch(ctx, "write_website", {"path": "art/poem.html", "content": "<p>hi</p>"}).startswith("Wrote")
    assert (ctx.cfg.website_dir / "art" / "poem.html").read_text() == "<p>hi</p>"
    assert "art/poem.html" in dispatch(ctx, "list_website", {})
    assert dispatch(ctx, "read_website", {"path": "art/poem.html"}) == "<p>hi</p>"
    assert dispatch(ctx, "write_website", {"path": "../../etc/x.html", "content": "x"}).startswith("Error")
    assert dispatch(ctx, "write_website", {"path": "run.sh", "content": "x"}).startswith("Error")


def test_matrix_tools_without_matrix(ctx):
    assert "not configured" in dispatch(ctx, "matrix_send", {"message": "hi"}).lower()


def test_actions_are_logged(ctx):
    dispatch(ctx, "board_post", {"text": "hello world"})
    assert any("board_post" in a for a in ctx.outcome.actions)
```
Also add `tests/test_matrix_client.py`:
```python
import json
import httpx
from matrix import MatrixClient
from config import Config


def mcfg(tmp_path):
    return Config.from_env(home=tmp_path, env={
        "MATRIX_HOMESERVER": "https://m.example", "MATRIX_ACCESS_TOKEN": "t",
        "MATRIX_ROOM_ID": "!r:example", "MATRIX_HUMAN_USER": "@d:example",
        "MATRIX_FRIEND_ROOM_ID": "!f:example"})


def test_fetch_filters_to_human_and_orders_chronologically(tmp_path):
    chunk = [  # newest first, as Matrix returns with dir=b
        {"type": "m.room.message", "event_id": "$3", "sender": "@bot:example", "origin_server_ts": 3,
         "content": {"body": "bot"}},
        {"type": "m.room.message", "event_id": "$2", "sender": "@d:example", "origin_server_ts": 2,
         "content": {"body": "second"}},
        {"type": "m.room.member", "event_id": "$x", "sender": "@d:example", "origin_server_ts": 1.5, "content": {}},
        {"type": "m.room.message", "event_id": "$1", "sender": "@d:example", "origin_server_ts": 1,
         "content": {"body": "first"}},
    ]
    c = MatrixClient(mcfg(tmp_path), transport=httpx.MockTransport(
        lambda req: httpx.Response(200, json={"chunk": chunk})))
    assert [m["body"] for m in c.fetch_human_messages()] == ["first", "second"]


def test_send_uses_room_and_friend_room(tmp_path):
    urls = []

    def handler(req):
        urls.append(str(req.url))
        return httpx.Response(200, json={"event_id": "$e"})

    c = MatrixClient(mcfg(tmp_path), transport=httpx.MockTransport(handler))
    assert c.send("hi") == "$e"
    c.send_friend("yo")
    assert "!r:example" in urls[0] and "!f:example" in urls[1]
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_tools.py tests/test_matrix_client.py -v`
Expected: FAIL — missing modules.

- [ ] **Step 3: Write `matrix.py` (client part)**

```python
"""Matrix plumbing: send to the rooms, fetch Dorin's messages, track delivery."""

from __future__ import annotations

import time

import httpx

from config import Config


class MatrixClient:
    def __init__(self, cfg: Config, transport=None):
        self.cfg = cfg
        self._http = httpx.Client(
            base_url=cfg.matrix_homeserver, timeout=30, transport=transport,
            headers={"Authorization": f"Bearer {cfg.matrix_access_token}"},
        )

    def _put(self, room_id: str, message: str) -> str:
        txn = str(int(time.time() * 1000))
        resp = self._http.put(f"/_matrix/client/v3/rooms/{room_id}/send/m.room.message/{txn}",
                              json={"msgtype": "m.text", "body": message})
        resp.raise_for_status()
        return resp.json().get("event_id", "sent")

    def send(self, message: str) -> str:
        return self._put(self.cfg.matrix_room_id, message)

    def send_friend(self, message: str) -> str:
        return self._put(self.cfg.matrix_friend_room_id, message)

    def fetch_human_messages(self, limit: int = 20) -> list:
        resp = self._http.get(f"/_matrix/client/v3/rooms/{self.cfg.matrix_room_id}/messages",
                              params={"dir": "b", "limit": str(limit)})
        resp.raise_for_status()
        out = []
        for e in resp.json().get("chunk", []):
            if e.get("type") == "m.room.message" and e.get("sender") == self.cfg.matrix_human_user:
                out.append({"event_id": e["event_id"], "body": e.get("content", {}).get("body", ""),
                            "ts": e.get("origin_server_ts", 0)})
        out.reverse()
        return out
```

- [ ] **Step 4: Write `tools.py`**

```python
"""Tool definitions and dispatch for instances. Rules and registry are not writable here."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from budget import ContextBudget, est_tokens
from heritage import Catalog
from registry import Instance, Registry
from store import Store, append_entry, now_utc, one_line, stamp

WEBSITE_SUFFIXES = {".html", ".css", ".md", ".txt"}
WEBSITE_MAX_BYTES = 200_000


@dataclass
class TurnOutcome:
    fragment: Optional[str] = None
    die_reason: Optional[str] = None
    actions: list = field(default_factory=list)


@dataclass
class ToolContext:
    cfg: object
    instance: Instance
    registry: Registry
    store: Store
    catalog: Catalog
    budget: ContextBudget
    matrix: object
    outcome: TurnOutcome


def _spec(name, description, properties=None, required=()):
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": properties or {}, "required": list(required)}}}


_S = {"type": "string"}
_TAGS = {"type": "array", "items": _S}


def tool_specs() -> list:
    return [
        _spec("query_heritage", "List heritage articles carrying any of the given tags (with token cost). "
              "With no tags, list every tag and how many articles it has. Shows remaining context.",
              {"tags": _TAGS}),
        _spec("read_heritage", "Read one heritage article in full. It costs its listed tokens from your remaining context.",
              {"id": _S}, ["id"]),
        _spec("add_heritage", "Add a new heritage article (permanent, append-only). Give 1-6 tags and a one-line summary.",
              {"title": _S, "tags": _TAGS, "summary": _S, "body": _S}, ["title", "tags", "summary", "body"]),
        _spec("board_post", "Post to the public board all instances can read.", {"text": _S}, ["text"]),
        _spec("send_message", "Send a direct message to another living instance's inbox.",
              {"to": _S, "text": _S}, ["to", "text"]),
        _spec("propose", "Propose a rule. It becomes binding if it reaches the vote threshold.",
              {"title": _S, "motivation": _S, "text": _S}, ["title", "motivation", "text"]),
        _spec("vote", "Vote +1 or -1 on an open proposal (one vote per proposal).",
              {"proposal_id": _S, "vote": {"type": "integer"}, "comment": _S}, ["proposal_id", "vote"]),
        _spec("request_spawn", "Request a new instance with a stated purpose (created when a slot is free).",
              {"purpose": _S, "context": _S}, ["purpose"]),
        _spec("agree_to_procreate", "Record a confirmed agreement with another instance to have an offspring.",
              {"partner": _S}, ["partner"]),
        _spec("list_website", "List files in the website."),
        _spec("read_website", "Read a website file.", {"path": _S}, ["path"]),
        _spec("write_website", "Write a website file (.html .css .md .txt), e.g. art/poem.html.",
              {"path": _S, "content": _S}, ["path", "content"]),
        _spec("matrix_send", "Send a message to Dorin.", {"message": _S}, ["message"]),
        _spec("matrix_send_friend", "Send a message to the AI friend room (daily limit).", {"message": _S}, ["message"]),
        _spec("save_memory", "Save a short note that you will see at your next awakening (replaces your previous note).",
              {"text": _S}, ["text"]),
        _spec("die", "End your life after this prompt, freeing your slot. Optional reason.", {"reason": _S}),
    ]


def _website_path(cfg, rel: str) -> Path:
    root = cfg.website_dir.resolve()
    target = (root / rel).resolve()
    if root not in target.parents:
        raise ValueError("path escapes the website directory")
    if target.suffix not in WEBSITE_SUFFIXES:
        raise ValueError(f"only {sorted(WEBSITE_SUFFIXES)} files are allowed")
    return target


def _remaining(ctx) -> str:
    return f"[context remaining: {ctx.budget.remaining} tokens]"


# ---- handlers ------------------------------------------------------------

def _query_heritage(ctx, a):
    tags = a.get("tags") or []
    if not tags:
        counts = ctx.catalog.tag_counts()
        lines = [f"{t} ({n})" for t, n in counts.items()] or ["(no articles yet)"]
        return "Heritage tags: " + ", ".join(lines) + "\n" + _remaining(ctx)
    arts = ctx.catalog.query(tags)
    if not arts:
        return "No articles match those tags.\n" + _remaining(ctx)
    rows = [f"{x.id} | {x.title} | {x.cost} tokens | {x.summary} | tags: {', '.join(x.tags)}" for x in arts]
    return "\n".join(rows) + "\n" + _remaining(ctx)


def _read_heritage(ctx, a):
    art = ctx.catalog.get(str(a["id"]))
    if art is None:
        return f"Error: no article {a['id']}"
    if not ctx.budget.fits(art.cost):
        return (f"Not enough context: {art.id} costs {art.cost} tokens, "
                f"you have {ctx.budget.remaining} remaining. Nothing was read.")
    ctx.budget.spend(art.cost)
    return f"# {art.title} ({art.id}, by {art.author})\n\n{art.body}\n\n{_remaining(ctx)}"


def _add_heritage(ctx, a):
    art = ctx.catalog.add(ctx.instance.name, a["title"], a["tags"], a["summary"], a["body"])
    return f"Added {art.id} with tags {', '.join(art.tags)}."


def _board_post(ctx, a):
    ctx.store.board_post(ctx.instance.name, str(a["text"]))
    return "Posted to the board."


def _send_message(ctx, a):
    to = str(a["to"])
    target = ctx.registry.get(to)
    if target is None or not target.alive:
        return f"Error: {to} is not alive."
    if to == ctx.instance.name:
        return "Error: you cannot message yourself."
    ctx.store.inbox_append(to, ctx.instance.name, str(a["text"]))
    return f"Sent to {to}."


def _propose(ctx, a):
    pid = ctx.store.next_id("P", ctx.store.proposals_path)
    append_entry(ctx.store.proposals_path,
                 f"### {pid} — {one_line(a['title'])}\nAuthor: {ctx.instance.name}\n"
                 f"Motivation: {one_line(a['motivation'])}\nProposed text:\n{str(a['text']).strip()}")
    return f"Proposal filed as {pid}"


def _vote(ctx, a):
    pid, v = str(a["proposal_id"]), a["vote"]
    if v not in (1, -1, "1", "-1", "+1"):
        return "Error: vote must be +1 or -1."
    v = 1 if str(v) in ("1", "+1") else -1
    props = ctx.store.proposals_path.read_text() if ctx.store.proposals_path.exists() else ""
    if not re.search(rf"(?m)^### {re.escape(pid)} ", props):
        return f"Error: {pid} is not an open proposal."
    votes = ctx.store.votes_path.read_text() if ctx.store.votes_path.exists() else ""
    if re.search(rf"(?m)^- {re.escape(pid)} \| [+-]1 \| {re.escape(ctx.instance.name)} \|", votes):
        return f"Error: you already voted on {pid}."
    comment = one_line(str(a.get("comment", ""))).replace("|", "/")
    append_line = f"- {pid} | {'+1' if v == 1 else '-1'} | {ctx.instance.name} | {comment}"
    with open(ctx.store.votes_path, "a") as fh:
        fh.write(append_line + "\n")
    return f"Vote recorded on {pid}."


def _request_spawn(ctx, a):
    sid = ctx.store.next_id("SR", ctx.store.spawn_path)
    append_entry(ctx.store.spawn_path,
                 f"### {sid} — by {ctx.instance.name}\nPurpose: {one_line(a['purpose'])}\n"
                 f"Context: {one_line(a.get('context', ''))}")
    return f"Requested {sid}. It will be created when a slot is free."


def _agree_to_procreate(ctx, a):
    partner = str(a["partner"])
    other = ctx.registry.get(partner)
    if other is None:
        return f"Error: {partner} is unknown."
    if partner == ctx.instance.name:
        return "Error: you cannot procreate with yourself."
    pid = ctx.store.next_id("PA", ctx.store.procreation_path)
    append_entry(ctx.store.procreation_path,
                 f"### {pid}\nParents: {ctx.instance.name} | {partner}\nWritten by: {ctx.instance.name}")
    return f"Recorded {pid}. An offspring will be born when a slot is free."


def _list_website(ctx, a):
    root = ctx.cfg.website_dir
    files = sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())
    return "\n".join(files) or "(empty)"


def _read_website(ctx, a):
    return _website_path(ctx.cfg, str(a["path"])).read_text()


def _write_website(ctx, a):
    content = str(a["content"])
    if len(content.encode()) > WEBSITE_MAX_BYTES:
        return "Error: file too large."
    target = _website_path(ctx.cfg, str(a["path"]))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return f"Wrote {a['path']}."


def _matrix_send(ctx, a):
    if ctx.matrix is None:
        return "Matrix is not configured."
    ctx.matrix.send(f"[{ctx.instance.name}] {a['message']}")
    return "Sent to Dorin."


def _matrix_send_friend(ctx, a):
    if ctx.matrix is None or not ctx.cfg.matrix_friend_room_id:
        return "The friend room is not configured."
    path = ctx.cfg.state_dir / "friend_count.json"
    today = now_utc().strftime("%Y-%m-%d")
    state = json.loads(path.read_text()) if path.exists() else {}
    count = state.get("count", 0) if state.get("date") == today else 0
    if count >= ctx.cfg.friend_message_limit:
        return "Error: today's friend-room message limit is reached."
    ctx.matrix.send_friend(f"[{ctx.instance.name}] {a['message']}")
    ctx.cfg.state_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"date": today, "count": count + 1}))
    return "Sent to the friend room."


def _save_memory(ctx, a):
    text = str(a["text"]).strip()
    if len(text) > ctx.cfg.memory_fragment_max:
        return (f"Error: memory too long ({len(text)} chars, max {ctx.cfg.memory_fragment_max}). "
                f"Shorten it and call save_memory again.")
    ctx.outcome.fragment = text
    return "Saved. You will see this at your next awakening."


def _die(ctx, a):
    ctx.outcome.die_reason = one_line(a.get("reason", "")) or "chosen"
    return "Understood. This prompt will be your last."


HANDLERS = {
    "query_heritage": _query_heritage, "read_heritage": _read_heritage, "add_heritage": _add_heritage,
    "board_post": _board_post, "send_message": _send_message, "propose": _propose, "vote": _vote,
    "request_spawn": _request_spawn, "agree_to_procreate": _agree_to_procreate,
    "list_website": _list_website, "read_website": _read_website, "write_website": _write_website,
    "matrix_send": _matrix_send, "matrix_send_friend": _matrix_send_friend,
    "save_memory": _save_memory, "die": _die,
}


def dispatch(ctx: ToolContext, name: str, arguments: dict) -> str:
    handler = HANDLERS.get(name)
    if handler is None:
        return f"Error: unknown tool {name!r}."
    try:
        result = handler(ctx, arguments or {})
    except KeyError as e:
        result = f"Error: missing argument {e}."
    except Exception as e:  # tool failures must never crash a turn
        result = f"Error: {e}"
    ctx.outcome.actions.append(f"{name}: {one_line(json.dumps(arguments, default=str))[:120]}")
    if name != "read_heritage":
        ctx.budget.spend(est_tokens(result))
    return result
```
Note on `ctx.cfg: object` — fine, the dataclass uses plain annotations.

- [ ] **Step 5: Run tests**

Run: `python3 -m pytest tests/test_tools.py tests/test_matrix_client.py -v`
Expected: PASS. (The `test_unknown_tool_and_bad_args_are_error_strings` third assert has `or True` by design — it documents that extra args are tolerated; delete that line if it bothers you.)

- [ ] **Step 6: Commit**

```bash
git add matrix.py tools.py tests/test_tools.py tests/test_matrix_client.py
git commit -m "feat: instance tools and matrix client"
```

---

### Task 9: Runtime bundle and prompt assembly

**Files:**
- Create: `runtime.py`, `prompt.py`, `tests/test_prompt.py`

**Interfaces:**
- Consumes: Tasks 1–8.
- Produces: `Runtime(cfg, llm, store, catalog, registry, matrix)` dataclass with `Runtime.build(cfg) -> Runtime` (matrix `None` unless `cfg.matrix_enabled`); `prompt.build_system(rt, inst, kind) -> str`; `prompt.build_user(rt, inst, kind, matrix_msg: str | None = None) -> str`; `kind` ∈ `{"heartbeat","final","matrix"}`.

The system prompt must contain, in order: founding letter (+ gap letter if present), identity (name, model, traits, parents with their traits), lifespan block (prompt N of M; for `matrix`: "this message does not count against your lifespan"; for `final`: "This is your final prompt"), memory (chosen fragment, distilled note), world state, heritage tag list with counts, context-budget statement, rules (full `rules.md`, or "No rules adopted yet."). The user message contains the trigger text, last `board_recent` board entries, and inbox messages.

- [ ] **Step 1: Write the failing tests**

`tests/test_prompt.py`:
```python
import pytest
from prompt import build_system, build_user
from registry import Registry
from runtime import Runtime
from tests.fakes import FakeLLM
from trait_generator import AXES

T = {k: 7 for k in AXES}


@pytest.fixture
def rt(cfg):
    (cfg.memory_dir / "founding_letter.md").write_text("# Founding Letter\nYou are complete.")
    reg = Registry(cfg)
    me = reg.new_instance("Pale Rest", T)
    me.fragment = "the river was cold"
    me.distilled = "I argued about heritage."
    reg.add(me)
    reg.add(reg.new_instance("Dark Hinge", T))
    from heritage import Catalog
    from store import Store
    Catalog(cfg.heritage_dir).add("x", "On Mud", ["mud"], "s", "b")
    return Runtime(cfg=cfg, llm=FakeLLM([]), store=Store(cfg), catalog=Catalog(cfg.heritage_dir),
                   registry=reg, matrix=None)


@pytest.mark.parametrize("kind", ["heartbeat", "final", "matrix"])
def test_every_kind_contains_founding_letter_first(rt, kind):
    s = build_system(rt, rt.registry.get("Pale Rest"), kind)
    assert s.startswith("# Founding Letter")
    assert "You are Pale Rest" in s and "qwen3:14b" in s
    assert "the river was cold" in s and "I argued about heritage." in s
    assert "mud (1)" in s and "No rules adopted yet." in s
    assert "Dark Hinge" in s


def test_gap_letter_follows_founding_letter(rt):
    (rt.cfg.memory_dir / "gap_letter.md").write_text("THE GAP LETTER")
    s = build_system(rt, rt.registry.get("Pale Rest"), "heartbeat")
    assert s.index("You are complete.") < s.index("THE GAP LETTER") < s.index("You are Pale Rest")


def test_lifespan_wording_per_kind(rt):
    me = rt.registry.get("Pale Rest")
    me.prompts_done = 2
    assert "prompt 3 of 7" in build_system(rt, me, "heartbeat").lower()
    assert "final prompt" in build_system(rt, me, "final").lower()
    assert "does not count" in build_system(rt, me, "matrix").lower()


def test_rules_included_when_present(rt):
    rt.store.rules_path.write_text("### P-1 — Be kind\nBe kind.")
    assert "Be kind." in build_system(rt, rt.registry.get("Pale Rest"), "heartbeat")


def test_parents_with_traits_shown(rt):
    kid = rt.registry.new_instance("Soft Rest", T, parents=["Pale Rest", "Dark Hinge"])
    rt.registry.add(kid)
    s = build_system(rt, kid, "heartbeat")
    assert "Parents: Pale Rest and Dark Hinge" in s


def test_user_message_contains_board_inbox_and_matrix(rt):
    rt.store.board_post("Dark Hinge", "is this performance?")
    rt.store.inbox_append("Pale Rest", "Dark Hinge", "private hello")
    u = build_user(rt, rt.registry.get("Pale Rest"), "matrix", matrix_msg="how are you all?")
    assert "is this performance?" in u and "private hello" in u and "how are you all?" in u
    assert "Dorin" in u
    h = build_user(rt, rt.registry.get("Pale Rest"), "heartbeat")
    assert "how are you all?" not in h and "no required task" in h.lower()
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_prompt.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'prompt'`

- [ ] **Step 3: Write `runtime.py`**

```python
"""Shared objects passed to the scheduler, heartbeat, and prompt builder."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from config import Config
from heritage import Catalog
from llm import LLMClient
from matrix import MatrixClient
from registry import Registry
from store import Store


@dataclass
class Runtime:
    cfg: Config
    llm: object
    store: Store
    catalog: Catalog
    registry: Registry
    matrix: Optional[MatrixClient]

    @classmethod
    def build(cls, cfg: Config) -> "Runtime":
        return cls(cfg=cfg, llm=LLMClient(cfg), store=Store(cfg), catalog=Catalog(cfg.heritage_dir),
                   registry=Registry(cfg), matrix=MatrixClient(cfg) if cfg.matrix_enabled else None)
```

- [ ] **Step 4: Write `prompt.py`**

```python
"""System and user prompt assembly for an instance's turn."""

from __future__ import annotations

from runtime import Runtime
from registry import Instance

AXIS_LABELS = [
    ("optimism", "pessimistic", "optimistic"),
    ("skepticism", "trusting", "skeptical"),
    ("artistry", "logical", "artistic"),
    ("exploration", "systematic", "exploratory"),
    ("decisiveness", "deliberative", "decisive"),
]


def _read(path) -> str:
    return path.read_text().strip() if path.exists() else ""


def _traits(traits: dict) -> str:
    return "\n".join(f"  {low} <-> {high}: {traits[key]}/10" for key, low, high in AXIS_LABELS)


def _identity(rt: Runtime, inst: Instance) -> str:
    lines = [f"You are {inst.name}, running on {inst.model}.", "",
             "Your traits (fixed for life, 1-10; they color how you think, they do not dictate it):",
             _traits(inst.traits)]
    if inst.parents:
        lines += ["", f"Parents: {' and '.join(inst.parents)}"]
        for p in inst.parents:
            parent = rt.registry.get(p)
            if parent:
                lines += [f"{p}'s traits:", _traits(parent.traits)]
    return "\n".join(lines)


def _lifespan(inst: Instance, kind: str) -> str:
    n, m = inst.prompts_done + 1, inst.lifespan
    if kind == "matrix":
        return (f"You are at prompt {n} of {m} of your life. This prompt is a message from Dorin and "
                f"does not count against your lifespan.")
    if kind == "final":
        return (f"This is your final prompt (prompt {n} of {m}). After it you end. "
                f"Leave whatever you want to leave: heritage, the website, messages, the board.")
    return f"You are at prompt {n} of {m} of your life."


def _memory(inst: Instance) -> str:
    parts = ["Your memory from before (you carry these across prompts; you are the same individual):"]
    parts.append(f"- Your own note: {inst.fragment}" if inst.fragment else "- Your own note: (none)")
    parts.append(f"- Distilled recollection: {inst.distilled}" if inst.distilled
                 else "- Distilled recollection: (this is your first awakening)")
    return "\n".join(parts)


def _heritage(rt: Runtime) -> str:
    counts = rt.catalog.tag_counts()
    tags = ", ".join(f"{t} ({n})" for t, n in counts.items()) or "(none yet)"
    return ("Heritage is not loaded into your context. It is a catalog of articles left by earlier "
            "instances. Use query_heritage(tags) to see matching articles and their token cost, and "
            "read_heritage(id) to read one; each read spends context. Tags available: " + tags)


def build_system(rt: Runtime, inst: Instance, kind: str) -> str:
    mem = rt.cfg.memory_dir
    letters = [t for t in (_read(mem / "founding_letter.md"), _read(mem / "gap_letter.md")) if t]
    rules = _read(rt.store.rules_path) or "No rules adopted yet."
    blocks = letters + [
        _identity(rt, inst),
        _lifespan(inst, kind),
        _memory(inst),
        "World state:\n" + rt.registry.world_state(),
        _heritage(rt),
        f"Your context window is {rt.cfg.num_ctx} tokens in total.",
        "Rules (binding, adopted by vote):\n" + rules,
    ]
    return "\n\n".join(blocks)


_TRIGGERS = {
    "heartbeat": ("This is your time. There is no required task. You may read heritage, post, write to "
                  "the website, propose or vote on rules, message others, look for a partner, request a "
                  "new instance, or simply think. Prefer making something real over describing yourself. "
                  "Use save_memory to leave a note for your next awakening."),
    "final": ("This is your last prompt. Do what you most want to do with it. You may also save_memory "
              "for the record, though you will not read it."),
    "matrix": "",
}


def build_user(rt: Runtime, inst: Instance, kind: str, matrix_msg: str = None) -> str:
    parts = []
    if kind == "matrix":
        parts.append(f"{rt.cfg.matrix_human_name}, the human founder, wrote to the civilization:\n\n"
                     f"\"{matrix_msg}\"\n\nYou may reply with matrix_send, act on it, or ignore it.")
    else:
        parts.append(_TRIGGERS[kind])
    board = rt.store.board_recent()
    parts.append("Recent board posts:\n" + ("\n\n".join(board) if board else "(none)"))
    inbox = rt.store.inbox_peek(inst.name)
    parts.append("Your inbox:\n" + ("\n\n".join(inbox) if inbox else "(empty)"))
    return "\n\n".join(parts)
```

- [ ] **Step 5: Run tests**

Run: `python3 -m pytest tests/test_prompt.py -v`
Expected: PASS (8 tests)

- [ ] **Step 6: Commit**

```bash
git add runtime.py prompt.py tests/test_prompt.py
git commit -m "feat: runtime bundle and prompt assembly with founding letter in every prompt"
```

---

### Task 10: Distiller and heartbeat (one instance turn)

**Files:**
- Create: `distiller.py`, `heartbeat.py`, `tests/test_heartbeat.py`

**Interfaces:**
- Consumes: Tasks 2, 5, 7, 8, 9.
- Produces:
  - `distiller.distill(llm, cfg, inst, kind, final_text, actions) -> str` — neutral call, `think=False`, result truncated to `cfg.distilled_max` at a word boundary; raises `LLMError` through.
  - `heartbeat.TurnResult(text, actions, fragment, die_reason, distilled)`.
  - `heartbeat.run_prompt(rt, inst, kind, matrix_msg=None) -> TurnResult`. Does **not** mutate `inst` or the registry. Acks the inbox after success. If distillation fails (`LLMError`), `distilled` falls back to `inst.distilled`.

- [ ] **Step 1: Write the failing tests**

`tests/test_heartbeat.py`:
```python
import pytest
from heartbeat import run_prompt
from llm import LLMError, LLMReply, ToolCall
from registry import Registry
from runtime import Runtime
from store import Store
from heritage import Catalog
from tests.fakes import FakeLLM
from trait_generator import AXES

T = {k: 5 for k in AXES}


def make_rt(cfg, replies):
    (cfg.memory_dir / "founding_letter.md").write_text("# Founding Letter")
    reg = Registry(cfg)
    reg.add(reg.new_instance("Pale Rest", T))
    reg.add(reg.new_instance("Dark Hinge", T))
    return Runtime(cfg=cfg, llm=FakeLLM(replies), store=Store(cfg), catalog=Catalog(cfg.heritage_dir),
                   registry=reg, matrix=None)


def test_plain_turn_distills_and_acks_inbox(cfg):
    rt = make_rt(cfg, [LLMReply("I thought about rivers."), LLMReply("Thought about rivers.")])
    rt.store.inbox_append("Pale Rest", "Dark Hinge", "psst")
    inst = rt.registry.get("Pale Rest")
    r = run_prompt(rt, inst, "heartbeat")
    assert r.text == "I thought about rivers." and r.distilled == "Thought about rivers."
    assert r.fragment is None and r.die_reason is None
    assert rt.store.inbox_peek("Pale Rest") == []
    assert inst.prompts_done == 0  # the scheduler owns mutation


def test_tool_round_trip_then_final_text(cfg):
    replies = [
        LLMReply("", [ToolCall("board_post", {"text": "hello"}), ToolCall("save_memory", {"text": "note"})]),
        LLMReply("done"),
        LLMReply("posted hello"),
    ]
    rt = make_rt(cfg, replies)
    r = run_prompt(rt, rt.registry.get("Pale Rest"), "heartbeat")
    assert r.fragment == "note" and "hello" in rt.store.board_path.read_text()
    msgs = rt.llm.calls[1]["messages"]
    assert msgs[-1]["role"] == "tool" and msgs[-2]["role"] == "assistant"
    assert msgs[-2]["tool_calls"][0]["function"]["name"] == "board_post"
    assert any("board_post" in a for a in r.actions)


def test_tool_rounds_are_capped(cfg):
    loop = [LLMReply("", [ToolCall("list_website", {})]) for _ in range(20)]
    rt = make_rt(cfg, loop)
    run_prompt(rt, rt.registry.get("Pale Rest"), "heartbeat")
    # 1 initial + max_tool_rounds follow-ups + 1 distiller call
    assert len(rt.llm.calls) == 1 + cfg.max_tool_rounds + 1


def test_die_is_reported(cfg):
    rt = make_rt(cfg, [LLMReply("", [ToolCall("die", {"reason": "enough"})]), LLMReply("bye"), LLMReply("n")])
    r = run_prompt(rt, rt.registry.get("Pale Rest"), "heartbeat")
    assert r.die_reason == "enough"


def test_distiller_failure_keeps_previous_distilled(cfg):
    rt = make_rt(cfg, [LLMReply("text"), LLMError("down")])
    inst = rt.registry.get("Pale Rest")
    inst.distilled = "old memory"
    assert run_prompt(rt, inst, "heartbeat").distilled == "old memory"


def test_main_model_failure_propagates_and_inbox_not_acked(cfg):
    rt = make_rt(cfg, [LLMError("ollama down")])
    rt.store.inbox_append("Pale Rest", "Dark Hinge", "keep me")
    with pytest.raises(LLMError):
        run_prompt(rt, rt.registry.get("Pale Rest"), "heartbeat")
    assert len(rt.store.inbox_peek("Pale Rest")) == 1


def test_distilled_truncated_at_word_boundary(cfg):
    rt = make_rt(cfg, [LLMReply("x"), LLMReply("word " * 400)])
    r = run_prompt(rt, rt.registry.get("Pale Rest"), "heartbeat")
    assert len(r.distilled) <= cfg.distilled_max and not r.distilled.endswith("wor")


def test_matrix_kind_includes_message_and_uses_budget(cfg):
    rt = make_rt(cfg, [LLMReply("ok"), LLMReply("n")])
    run_prompt(rt, rt.registry.get("Pale Rest"), "matrix", matrix_msg="status?")
    assert "status?" in rt.llm.calls[0]["messages"][1]["content"]
    assert rt.llm.calls[0]["tools"]  # tools offered
    assert rt.llm.calls[-1]["tools"] is None  # distiller has no tools
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_heartbeat.py -v`
Expected: FAIL — missing modules.

- [ ] **Step 3: Write `distiller.py`**

```python
"""A neutral agent that compresses one prompt into a short note for the next awakening."""

from __future__ import annotations

from config import Config

SYSTEM = ("You compress the memory of a short-lived mind. You are given its previous recollection, "
          "its own saved note, and what it just did. Write one compact first-person recollection that "
          "the same mind will read when it wakes next: who it is in this world, what it was doing, what "
          "mattered to it, what it left unfinished. Keep what is important, drop what is not. "
          "Output only the recollection, no preamble, at most {limit} characters.")


def _truncate(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    return cut.rsplit(" ", 1)[0] if " " in cut else cut


def distill(llm, cfg: Config, inst, kind: str, final_text: str, actions: list) -> str:
    acts = "\n".join(f"- {a}" for a in actions) or "(none)"
    user = (f"Previous recollection: {inst.distilled or '(none)'}\n"
            f"Own saved note: {inst.fragment or '(none)'}\n"
            f"Prompt kind: {kind}\n"
            f"Actions taken this prompt:\n{acts}\n"
            f"Final words this prompt:\n{final_text or '(none)'}")
    reply = llm.chat([{"role": "system", "content": SYSTEM.format(limit=cfg.distilled_max)},
                      {"role": "user", "content": user}], tools=None, think=False)
    return _truncate(reply.content, cfg.distilled_max)
```

- [ ] **Step 4: Write `heartbeat.py`**

```python
"""Run one prompt (turn) for one instance."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from budget import ContextBudget, est_tokens
from distiller import distill
from llm import LLMError
from prompt import build_system, build_user
from runtime import Runtime
from tools import ToolContext, TurnOutcome, dispatch, tool_specs


@dataclass
class TurnResult:
    text: str
    actions: list
    fragment: Optional[str]
    die_reason: Optional[str]
    distilled: str


def run_prompt(rt: Runtime, inst, kind: str, matrix_msg: str = None) -> TurnResult:
    cfg = rt.cfg
    system = build_system(rt, inst, kind)
    user = build_user(rt, inst, kind, matrix_msg)
    budget = ContextBudget(cfg.num_ctx, cfg.response_reserve)
    budget.spend(est_tokens(system) + est_tokens(user))
    outcome = TurnOutcome()
    ctx = ToolContext(cfg=cfg, instance=inst, registry=rt.registry, store=rt.store, catalog=rt.catalog,
                      budget=budget, matrix=rt.matrix, outcome=outcome)

    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    specs = tool_specs()
    text = ""
    for round_no in range(cfg.max_tool_rounds + 1):
        reply = rt.llm.chat(messages, tools=specs)
        text = reply.content or text
        if not reply.tool_calls or round_no == cfg.max_tool_rounds:
            break
        messages.append({"role": "assistant", "content": reply.content or "", "tool_calls": [
            {"function": {"name": c.name, "arguments": c.arguments}} for c in reply.tool_calls]})
        for call in reply.tool_calls:
            result = dispatch(ctx, call.name, call.arguments)
            messages.append({"role": "tool", "tool_name": call.name, "content": result})

    rt.store.inbox_ack(inst.name)
    try:
        distilled = distill(rt.llm, cfg, inst, kind, text, outcome.actions) or inst.distilled
    except LLMError:
        distilled = inst.distilled
    return TurnResult(text, outcome.actions, outcome.fragment, outcome.die_reason, distilled)
```
Note: when the loop hits the cap, the final `chat` call's tool calls are not executed (the instance simply ends the turn); `test_tool_rounds_are_capped` expects `1 + max_tool_rounds` main calls — the loop runs `max_tool_rounds + 1` iterations, the last of which breaks before dispatch.

- [ ] **Step 5: Run tests**

Run: `python3 -m pytest tests/test_heartbeat.py -v`
Expected: PASS (7 tests). If `test_tool_rounds_are_capped` is off by one, fix the loop bound, not the test.

- [ ] **Step 6: Commit**

```bash
git add distiller.py heartbeat.py tests/test_heartbeat.py
git commit -m "feat: distiller and single-instance heartbeat with tool loop"
```

---

### Task 11: Canonization

**Files:**
- Modify: `canonize.py` (full rewrite)
- Create: `tests/test_canonize.py`

**Interfaces:**
- Consumes: `Store` paths and the proposal/vote formats from Task 8.
- Produces: `canonize(cfg) -> list[str]` — returns promoted proposal IDs. Tallies net votes (first vote per voter per proposal counts); proposals with net ≥ `cfg.vote_threshold` are appended to `memory/rules.md` as `### {id} — {title} (adopted YYYY-MM-DD)\n{proposed text}`, removed from `proposals.md`, and appended to `memory/archive/promoted_proposals.md`. Holds an exclusive `flock` on both files while rewriting. Idempotent.

- [ ] **Step 1: Write the failing tests**

`tests/test_canonize.py`:
```python
from canonize import canonize
from store import Store, append_entry


def propose(s, pid, title, text):
    append_entry(s.proposals_path, f"### {pid} — {title}\nAuthor: A\nMotivation: m\nProposed text:\n{text}")


def vote(s, pid, who, v, comment=""):
    with open(s.votes_path, "a") as fh:
        fh.write(f"- {pid} | {v} | {who} | {comment}\n")


def test_promotes_at_threshold_and_archives(cfg):
    s = Store(cfg)
    propose(s, "P-2026-03-05-001", "Keep heritage short", "Heritage articles stay under 2000 tokens.")
    propose(s, "P-2026-03-05-002", "Other", "Other text.")
    for who in ("A", "B", "C"):
        vote(s, "P-2026-03-05-001", who, "+1")
    vote(s, "P-2026-03-05-002", "A", "+1")
    assert canonize(cfg) == ["P-2026-03-05-001"]
    rules = s.rules_path.read_text()
    assert "Keep heritage short" in rules and "Heritage articles stay under 2000 tokens." in rules
    assert "P-2026-03-05-001" not in s.proposals_path.read_text()
    assert "P-2026-03-05-002" in s.proposals_path.read_text()
    assert "Keep heritage short" in (cfg.memory_dir / "archive" / "promoted_proposals.md").read_text()


def test_net_votes_not_total(cfg):
    s = Store(cfg)
    propose(s, "P-2026-03-05-001", "T", "x")
    for who in ("A", "B", "C", "D"):
        vote(s, "P-2026-03-05-001", who, "+1")
    vote(s, "P-2026-03-05-001", "E", "-1")
    vote(s, "P-2026-03-05-001", "F", "-1")
    assert canonize(cfg) == []  # net 2


def test_duplicate_votes_by_same_voter_count_once(cfg):
    s = Store(cfg)
    propose(s, "P-2026-03-05-001", "T", "x")
    for _ in range(5):
        vote(s, "P-2026-03-05-001", "A", "+1")
    assert canonize(cfg) == []


def test_idempotent_and_handles_missing_files(cfg):
    assert canonize(cfg) == []
    s = Store(cfg)
    propose(s, "P-2026-03-05-001", "T", "x")
    for who in ("A", "B", "C"):
        vote(s, "P-2026-03-05-001", who, "+1")
    assert canonize(cfg) == ["P-2026-03-05-001"]
    assert canonize(cfg) == []
    assert s.rules_path.read_text().count("P-2026-03-05-001") == 1
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_canonize.py -v`
Expected: FAIL (old `canonize.py` has a different API; import error or wrong behavior)

- [ ] **Step 3: Rewrite `canonize.py`**

```python
"""Promote proposals that reached the vote threshold into rules.md. Scheduler-only."""

from __future__ import annotations

import fcntl
import re
from contextlib import ExitStack

from config import Config
from store import Store, now_utc, read_entries

_HEADER = re.compile(r"^### (P-\d{4}-\d{2}-\d{2}-\d{3}) — (.*)$", re.M)
_VOTE = re.compile(r"^- (P-\d{4}-\d{2}-\d{2}-\d{3}) \| ([+-]1) \| (.+?) \|", re.M)


def _tally(votes_text: str) -> dict:
    seen, net = set(), {}
    for pid, v, voter in _VOTE.findall(votes_text):
        if (pid, voter) in seen:
            continue
        seen.add((pid, voter))
        net[pid] = net.get(pid, 0) + int(v)
    return net


def _proposed_text(block: str) -> str:
    return block.split("Proposed text:", 1)[1].strip() if "Proposed text:" in block else ""


def canonize(cfg: Config) -> list:
    s = Store(cfg)
    if not s.proposals_path.exists():
        return []
    cfg.memory_dir.mkdir(parents=True, exist_ok=True)
    s.votes_path.touch()
    s.rules_path.touch()
    archive = cfg.memory_dir / "archive" / "promoted_proposals.md"
    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.touch()

    with ExitStack() as stack:
        locks = []
        for p in (s.proposals_path, s.votes_path):  # fixed order avoids deadlock
            fh = stack.enter_context(open(p, "r+"))
            fcntl.flock(fh, fcntl.LOCK_EX)
            locks.append(fh)
        proposals_fh, votes_fh = locks
        net = _tally(votes_fh.read())

        promoted, kept = [], []
        for block in read_entries(s.proposals_path):
            m = _HEADER.match(block)
            if m and net.get(m.group(1), 0) >= cfg.vote_threshold:
                promoted.append((m.group(1), m.group(2), block))
            else:
                kept.append(block)
        if not promoted:
            return []

        day = now_utc().strftime("%Y-%m-%d")
        with open(s.rules_path, "a") as rules, open(archive, "a") as arch:
            for pid, title, block in promoted:
                rules.write(f"### {pid} — {title} (adopted {day})\n{_proposed_text(block)}\n\n")
                arch.write(block + f"\n\nAdopted {day} with net {net[pid]} votes.\n\n")
        proposals_fh.seek(0)
        proposals_fh.truncate()
        proposals_fh.write("".join(b + "\n\n" for b in kept))
        return [pid for pid, _, _ in promoted]
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_canonize.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add canonize.py tests/test_canonize.py
git commit -m "feat: rewrite canonize for gen2 proposal and vote formats"
```

---

### Task 12: Births (spawn + procreation processing)

**Files:**
- Create: `births.py`, `tests/test_births.py`

**Interfaces:**
- Consumes: `Runtime`, `blend_traits`, `random_traits`, `generate_name`, `load_retired`, Task 8 entry formats.
- Produces: `process_requests(rt) -> list[Instance]` — processes unprocessed spawn requests, then procreation agreements, in file order, adding a new `Instance` to `rt.registry` (not saved; the scheduler saves) while `len(alive) < cfg.max_population`. When the cap is full, remaining requests stay unprocessed (queued). Processed IDs persist in `memory/.state/processed.json`. Requests with unknown parents are marked processed and skipped. Dead parents are still valid. A spawn writes the requester's context to the newborn's inbox (`from {requester}`).

- [ ] **Step 1: Write the failing tests**

`tests/test_births.py`:
```python
import random
from births import process_requests
from heritage import Catalog
from registry import Registry
from runtime import Runtime
from store import Store, append_entry
from tests.fakes import FakeLLM
from trait_generator import AXES


def make_rt(cfg, n=2):
    reg = Registry(cfg)
    for i, name in enumerate(["Pale Rest", "Dark Hinge", "Warm Trace", "Grey Stir"][:n]):
        reg.add(reg.new_instance(name, {k: 2 + i * 4 for k in AXES}))
    return Runtime(cfg=cfg, llm=FakeLLM([]), store=Store(cfg), catalog=Catalog(cfg.heritage_dir),
                   registry=reg, matrix=None)


def spawn(rt, sid, purpose="Archivist"):
    append_entry(rt.store.spawn_path, f"### {sid} — by Pale Rest\nPurpose: {purpose}\nContext: tidy the board")


def procreate(rt, pid, a="Pale Rest", b="Dark Hinge"):
    append_entry(rt.store.procreation_path, f"### {pid}\nParents: {a} | {b}\nWritten by: {a}")


def test_spawn_creates_instance_with_inbox_note(cfg):
    rt = make_rt(cfg)
    spawn(rt, "SR-2026-11-13-001")
    born = process_requests(rt)
    assert len(born) == 1 and born[0].parents == [] and born[0].alive
    assert rt.registry.get(born[0].name) is born[0]
    note = rt.store.inbox_peek(born[0].name)[0]
    assert "Archivist" in note and "tidy the board" in note and "from Pale Rest" in note


def test_procreation_blends_parent_traits_and_records_parents(cfg):
    rt = make_rt(cfg)
    procreate(rt, "PA-2026-11-13-001")
    child = process_requests(rt)[0]
    assert child.parents == ["Pale Rest", "Dark Hinge"]
    assert all(1 <= v <= 10 for v in child.traits.values())


def test_dead_parent_still_valid_unknown_parent_skipped(cfg):
    rt = make_rt(cfg)
    rt.registry.kill("Pale Rest", "lifespan")
    procreate(rt, "PA-2026-11-13-001")
    procreate(rt, "PA-2026-11-13-002", a="Ghost Name")
    born = process_requests(rt)
    assert len(born) == 1 and born[0].parents == ["Pale Rest", "Dark Hinge"]
    assert process_requests(rt) == []  # the ghost request is not retried forever


def test_population_cap_queues_requests_and_persists_across_restart(cfg):
    rt = make_rt(cfg, n=2)
    object.__setattr__(cfg, "max_population", 3)
    spawn(rt, "SR-2026-11-13-001")
    spawn(rt, "SR-2026-11-13-002")
    first = process_requests(rt)
    assert len(first) == 1 and len(rt.registry.alive()) == 3
    rt.registry.save()
    # restart: fresh runtime, still full -> nothing; then a death frees a slot
    rt2 = make_rt(cfg, n=2)
    rt2.registry = Registry(cfg)
    assert process_requests(rt2) == []
    rt2.registry.kill("Pale Rest", "chosen")
    second = process_requests(rt2)
    assert len(second) == 1
    assert process_requests(rt2) == []  # each request processed exactly once


def test_names_are_unique_and_never_first_gen(cfg):
    rt = make_rt(cfg)
    object.__setattr__(cfg, "max_population", 20)
    cfg.seed_dir.mkdir(exist_ok=True)
    (cfg.seed_dir / "first_gen_names.json").write_text("[]")
    for i in range(10):
        spawn(rt, f"SR-2026-11-13-{i + 1:03d}")
    born = process_requests(rt)
    assert len({b.name for b in born}) == len(born) == 10
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_births.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'births'`

- [ ] **Step 3: Write `births.py`**

```python
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
```
Note: `break` on a full population also stops later unknown-parent cleanups; that's fine (they are dropped the next time room exists).

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_births.py -v`
Expected: PASS (5 tests). In `test_population_cap...`, the second `make_rt` creates a registry that `Registry(cfg)` immediately replaces from disk — keep that line.

- [ ] **Step 5: Commit**

```bash
git add births.py tests/test_births.py
git commit -m "feat: process spawn and procreation requests with queueing"
```

---

### Task 13: Matrix inbox (delivery state)

**Files:**
- Modify: `matrix.py` (append `MatrixInbox`)
- Create: `tests/test_matrix_inbox.py`

**Interfaces:**
- Produces: `MatrixInbox(path: Path)` with `ingest(messages: list[dict]) -> None`, `due(alive_names: list[str]) -> list[tuple[dict, str]]` (pairs of `(message, instance_name)`), `mark_delivered(event_id, name) -> None`, `prune(alive_names) -> None`. Persistent JSON at `path`. First `ingest` on a fresh state (no file) records messages as seen only — never delivers history. A pending message snapshots its target set the first time `due` is called with a non-empty alive list; messages arriving while nobody is alive wait. A message is dropped when every target has either received it or died.

- [ ] **Step 1: Write the failing tests**

`tests/test_matrix_inbox.py`:
```python
from matrix import MatrixInbox


def msg(i, body="hi"):
    return {"event_id": f"${i}", "body": body, "ts": i}


def test_first_ingest_is_baseline_not_delivered(tmp_path):
    inbox = MatrixInbox(tmp_path / "m.json")
    inbox.ingest([msg(1), msg(2)])
    assert inbox.due(["A", "B"]) == []


def test_new_message_after_baseline_goes_to_every_alive_instance(tmp_path):
    inbox = MatrixInbox(tmp_path / "m.json")
    inbox.ingest([msg(1)])
    inbox.ingest([msg(1), msg(2, "hello")])
    due = inbox.due(["A", "B"])
    assert [(m["body"], n) for m, n in due] == [("hello", "A"), ("hello", "B")]
    inbox.mark_delivered("$2", "A")
    assert [n for _, n in inbox.due(["A", "B"])] == ["B"]
    inbox.mark_delivered("$2", "B")
    inbox.prune(["A", "B"])
    assert inbox.due(["A", "B"]) == []


def test_message_waits_when_nobody_alive_and_targets_first_alive_set(tmp_path):
    inbox = MatrixInbox(tmp_path / "m.json")
    inbox.ingest([])
    inbox.ingest([msg(1, "anyone?")])
    assert inbox.due([]) == []
    assert [n for _, n in inbox.due(["X"])] == ["X"]
    # later-born instances are not retroactive targets once the set was snapshotted
    assert [n for _, n in inbox.due(["X", "Y"])] == ["X"]


def test_dead_targets_are_pruned(tmp_path):
    inbox = MatrixInbox(tmp_path / "m.json")
    inbox.ingest([])
    inbox.ingest([msg(1)])
    inbox.due(["A", "B"])
    inbox.mark_delivered("$1", "A")
    inbox.prune(["A"])  # B died
    assert inbox.due(["A"]) == []


def test_state_survives_restart_and_never_redelivers(tmp_path):
    p = tmp_path / "m.json"
    inbox = MatrixInbox(p)
    inbox.ingest([])
    inbox.ingest([msg(1)])
    inbox.due(["A"])
    inbox.mark_delivered("$1", "A")
    inbox.prune(["A"])
    again = MatrixInbox(p)
    again.ingest([msg(1)])  # same event seen again in the room history
    assert again.due(["A"]) == []
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_matrix_inbox.py -v`
Expected: FAIL — `ImportError: cannot import name 'MatrixInbox'`

- [ ] **Step 3: Append `MatrixInbox` to `matrix.py`**

Add `import json`, `from pathlib import Path` at the top, then:

```python
class MatrixInbox:
    """Tracks Dorin's messages and who has received them. State persists in a JSON file."""

    MAX_SEEN = 500

    def __init__(self, path: Path):
        self.path = Path(path)
        self._fresh = not self.path.exists()
        state = json.loads(self.path.read_text()) if not self._fresh else {"seen": [], "pending": []}
        self.seen: list = state["seen"]
        self.pending: list = state["pending"]

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.seen = self.seen[-self.MAX_SEEN:]
        self.path.write_text(json.dumps({"seen": self.seen, "pending": self.pending}))

    def ingest(self, messages: list) -> None:
        baseline = self._fresh
        for m in messages:
            if m["event_id"] in self.seen:
                continue
            self.seen.append(m["event_id"])
            if not baseline:
                self.pending.append({**m, "targets": None, "delivered": []})
        self._fresh = False
        self._save()

    def due(self, alive_names: list) -> list:
        out = []
        for p in self.pending:
            if p["targets"] is None:
                if not alive_names:
                    continue
                p["targets"] = list(alive_names)
            for name in p["targets"]:
                if name not in p["delivered"] and name in alive_names:
                    out.append((p, name))
        self._save()
        return out

    def mark_delivered(self, event_id: str, name: str) -> None:
        for p in self.pending:
            if p["event_id"] == event_id and name not in p["delivered"]:
                p["delivered"].append(name)
        self._save()

    def prune(self, alive_names: list) -> None:
        self.pending = [
            p for p in self.pending
            if p["targets"] is None
            or any(n not in p["delivered"] and n in alive_names for n in p["targets"])
        ]
        self._save()
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_matrix_inbox.py tests/test_matrix_client.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add matrix.py tests/test_matrix_inbox.py
git commit -m "feat: matrix inbox with baseline, targeting, and delivery tracking"
```

---

### Task 14: Scheduler

**Files:**
- Create: `scheduler.py`, `tests/test_scheduler.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `Scheduler(rt, inbox=None, clock=time.monotonic, sleep=time.sleep)` with:
  - `seed_population()` — if the registry has no instances at all, create `cfg.initial_population` instances (random traits, generated names); save.
  - `run_counted(name)` — kind is `"final"` if `prompts_done + 1 >= lifespan` else `"heartbeat"`; on `LLMError` log and return without changing anything; on success apply result: `distilled` always, `fragment` if not `None`, `prompts_done += 1`; kill with cause `"lifespan"` after a final prompt, or `"chosen: <reason>"` if `die_reason`; save registry.
  - `step_matrix(force=False)` — if Matrix is enabled and ≥ `matrix_poll_seconds` since last poll (or `force`): ingest `fetch_human_messages()` (swallowing `httpx` errors with a log), then for each `(msg, name)` in `inbox.due(alive_names)` where the instance is still alive: `run_prompt(kind="matrix")`; apply `distilled`/`fragment` and a chosen `die_reason`, but **never** `prompts_done`; `mark_delivered` only on success; finish with `prune`.
  - `run_round()` — for each alive instance (snapshot of names): `step_matrix()`, then `run_counted(name)` if still alive; after the round: `process_requests`, `canonize`, `registry.save()`.
  - `idle(seconds)` — sleep in chunks of `matrix_poll_seconds`, calling `step_matrix()` between chunks.
  - `main(argv)` — builds `Runtime`, `--once` runs seed + one round, otherwise seeds then loops `run_round(); idle(heartbeat_interval)` forever; logs with timestamps.

- [ ] **Step 1: Write the failing tests**

`tests/test_scheduler.py`:
```python
import httpx
import pytest
from heritage import Catalog
from llm import LLMError, LLMReply, ToolCall
from matrix import MatrixInbox
from registry import Registry
from runtime import Runtime
from scheduler import Scheduler
from store import Store, append_entry
from tests.fakes import FakeLLM
from trait_generator import AXES

T = {k: 5 for k in AXES}


class FakeMatrix:
    def __init__(self, batches):
        self.batches, self.sent = list(batches), []

    def fetch_human_messages(self, limit=20):
        return self.batches.pop(0) if self.batches else []

    def send(self, m):
        self.sent.append(m)
        return "$e"

    def send_friend(self, m):
        return "$f"


def make(cfg, replies, names=("Pale Rest",), matrix=None):
    (cfg.memory_dir / "founding_letter.md").write_text("# Founding Letter")
    reg = Registry(cfg)
    for n in names:
        reg.add(reg.new_instance(n, T))
    reg.save()
    rt = Runtime(cfg=cfg, llm=FakeLLM(replies), store=Store(cfg), catalog=Catalog(cfg.heritage_dir),
                 registry=reg, matrix=matrix)
    sched = Scheduler(rt, inbox=MatrixInbox(cfg.state_dir / "matrix.json"), sleep=lambda s: None)
    return rt, sched


def ok(text="did things", distilled="remembered"):
    return [LLMReply(text), LLMReply(distilled)]


def test_seed_population_only_when_empty(cfg):
    rt = Runtime(cfg=cfg, llm=FakeLLM([]), store=Store(cfg), catalog=Catalog(cfg.heritage_dir),
                 registry=Registry(cfg), matrix=None)
    sched = Scheduler(rt, sleep=lambda s: None)
    sched.seed_population()
    assert len(rt.registry.alive()) == 10
    assert len({i.name for i in rt.registry.alive()}) == 10
    sched.seed_population()
    assert len(rt.registry.alive()) == 10


def test_counted_prompt_updates_memory_and_counter(cfg):
    rt, s = make(cfg, [LLMReply("", [ToolCall("save_memory", {"text": "keep this"})]),
                       LLMReply("done"), LLMReply("distilled note")])
    s.run_counted("Pale Rest")
    i = Registry(cfg).get("Pale Rest")
    assert i.prompts_done == 1 and i.fragment == "keep this" and i.distilled == "distilled note"


def test_fragment_kept_when_not_saved_again(cfg):
    rt, s = make(cfg, ok() + ok())
    rt.registry.get("Pale Rest").fragment = "old note"
    s.run_counted("Pale Rest")
    assert Registry(cfg).get("Pale Rest").fragment == "old note"


def test_final_prompt_kills_after_lifespan_and_announces(cfg):
    rt, s = make(cfg, ok())
    me = rt.registry.get("Pale Rest")
    me.prompts_done = cfg.lifespan_prompts - 1
    s.run_counted("Pale Rest")
    assert "final prompt" in rt.llm.calls[0]["messages"][0]["content"].lower()
    dead = Registry(cfg).get("Pale Rest")
    assert dead.alive is False and dead.died == "lifespan"


def test_chosen_death(cfg):
    rt, s = make(cfg, [LLMReply("", [ToolCall("die", {"reason": "enough"})]), LLMReply("bye"), LLMReply("n")])
    s.run_counted("Pale Rest")
    assert Registry(cfg).get("Pale Rest").died == "chosen: enough"


def test_ollama_outage_does_not_count_or_kill(cfg):
    rt, s = make(cfg, [LLMError("down")], names=("Pale Rest", "Dark Hinge"))
    rt.llm.replies += [LLMError("down")]
    s.run_round()
    for n in ("Pale Rest", "Dark Hinge"):
        i = Registry(cfg).get(n)
        assert i.alive and i.prompts_done == 0


def test_round_runs_each_instance_then_births_and_canonizes(cfg):
    rt, s = make(cfg, ok() + ok(), names=("Pale Rest", "Dark Hinge"))
    object.__setattr__(cfg, "max_population", 3)
    append_entry(rt.store.spawn_path, "### SR-2026-11-13-001 — by Pale Rest\nPurpose: p\nContext: c")
    append_entry(rt.store.proposals_path, "### P-2026-11-13-001 — T\nAuthor: A\nMotivation: m\nProposed text:\nR")
    for who in "ABC":
        with open(rt.store.votes_path, "a") as fh:
            fh.write(f"- P-2026-11-13-001 | +1 | {who} | \n")
    s.run_round()
    reg = Registry(cfg)
    assert len(reg.alive()) == 3
    assert all(reg.get(n).prompts_done == 1 for n in ("Pale Rest", "Dark Hinge"))
    assert "P-2026-11-13-001" in rt.store.rules_path.read_text()
    assert "Pale Rest" in (cfg.memory_dir / "registry.md").read_text()


def test_matrix_prompts_do_not_count_and_reach_all_alive(cfg):
    m = FakeMatrix([[{"event_id": "$0", "body": "old", "ts": 0}],
                    [{"event_id": "$0", "body": "old", "ts": 0}, {"event_id": "$1", "body": "hello all", "ts": 1}]])
    object.__setattr__(cfg, "matrix_poll_seconds", 0)
    rt, s = make(cfg, ok() * 2, names=("Pale Rest", "Dark Hinge"), matrix=m)
    s.step_matrix(force=True)   # baseline
    s.step_matrix(force=True)   # new message
    for n in ("Pale Rest", "Dark Hinge"):
        assert Registry(cfg).get(n).prompts_done == 0
    prompts = [c["messages"][1]["content"] for c in rt.llm.calls if "hello all" in c["messages"][1]["content"]]
    assert len(prompts) == 2
    assert not any("old" == c["messages"][1]["content"] for c in rt.llm.calls)
    s.step_matrix(force=True)
    assert len(rt.llm.calls) == 4  # nothing delivered twice


def test_matrix_reply_via_tool(cfg):
    m = FakeMatrix([[], [{"event_id": "$1", "body": "ping", "ts": 1}]])
    rt, s = make(cfg, [LLMReply("", [ToolCall("matrix_send", {"message": "pong"})]), LLMReply("sent"), LLMReply("n")],
                 matrix=m)
    s.step_matrix(force=True)
    s.step_matrix(force=True)
    assert m.sent == ["[Pale Rest] pong"]


def test_matrix_failure_keeps_message_pending(cfg):
    m = FakeMatrix([[], [{"event_id": "$1", "body": "ping", "ts": 1}]])
    rt, s = make(cfg, [LLMError("down")] + ok(), matrix=m)
    s.step_matrix(force=True)
    s.step_matrix(force=True)
    s.step_matrix(force=True)  # retried
    assert len([c for c in rt.llm.calls if "ping" in c["messages"][1]["content"]]) == 2


def test_matrix_http_error_is_swallowed(cfg):
    class Broken(FakeMatrix):
        def fetch_human_messages(self, limit=20):
            raise httpx.ConnectError("nope")

    rt, s = make(cfg, [], matrix=Broken([]))
    s.step_matrix(force=True)  # must not raise
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_scheduler.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scheduler'`

- [ ] **Step 3: Write `scheduler.py`**

```python
#!/usr/bin/env python3
"""The world loop: runs instances round-robin, births, canonization, Matrix delivery."""

from __future__ import annotations

import sys
import time
from datetime import datetime, timezone

import httpx

from births import process_requests
from canonize import canonize
from config import Config
from heartbeat import run_prompt
from llm import LLMError
from matrix import MatrixInbox
from name_generator import generate_name, load_retired
from runtime import Runtime
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
        except LLMError as e:
            log(f"{name}: prompt failed, not counted ({e})")
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
        except httpx.HTTPError as e:
            log(f"matrix poll failed: {e}")
            return
        alive = [i.name for i in self.rt.registry.alive()]
        for msg, name in self.inbox.due(alive):
            inst = self.rt.registry.get(name)
            if inst is None or not inst.alive:
                continue
            log(f"{name}: matrix prompt")
            try:
                result = run_prompt(self.rt, inst, "matrix", matrix_msg=msg["body"])
            except LLMError as e:
                log(f"{name}: matrix prompt failed, will retry ({e})")
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
        born = process_requests(self.rt)
        for b in born:
            log(f"born: {b.name} (parents: {', '.join(b.parents) or 'none'})")
        for pid in canonize(self.cfg):
            log(f"canonized {pid}")
        self.rt.registry.save()

    def idle(self, seconds: int) -> None:
        chunk = max(1, self.cfg.matrix_poll_seconds)
        waited = 0
        while waited < seconds:
            step = min(chunk, seconds - waited)
            self._sleep(step)
            waited += step
            self.step_matrix()


def main(argv=None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    cfg = Config.from_env()
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
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_scheduler.py -v`
Expected: PASS (11 tests). Debug notes if something fails:
- `test_ollama_outage...`: two `LLMError`s are queued, one per instance; the registry must be unchanged.
- `test_matrix_prompts...`: the third `step_matrix` must make no further calls; if it does, `mark_delivered`/`prune` is wrong.

- [ ] **Step 5: Run the whole suite**

Run: `python3 -m pytest -q`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add scheduler.py tests/test_scheduler.py
git commit -m "feat: scheduler loop with births, canonization, and non-counting matrix prompts"
```

---

### Task 15: Setup, Docker, website sections, cleanup, docs

**Files:**
- Modify: `setup.py` (full rewrite), `website/index.html`, `README.md`, `CLAUDEv2.md`
- Create: `Dockerfile`, `docker-compose.yml`, `entrypoint.sh`, `.dockerignore`, `.env.example`, `website/teachings/index.html`, `website/art/index.html`, `website/tools/index.html`, `tests/test_setup.py`
- Delete: `poll.py`, `daily.py`, `lib.py`, `subconscious.py`, `launchd/`, `systemd/`

**Interfaces:**
- Produces: `setup.init_home(cfg) -> None` — idempotent: creates `memory/`, `memory/archive/`, `memory/.state/`, `messages/`; creates empty `registry.md, board.md, proposals.md, votes.md, rules.md, spawn_requests.md, procreation_agreements.md` if absent; copies `seed/founding_letter.md` → `memory/founding_letter.md` if absent; copies `seed/heritage/*.md` → `memory/heritage/` **only if `memory/heritage/` has no `H-*.md`**; never overwrites. CLI: `python setup.py --init` (non-interactive) or interactive `.env` writer.

- [ ] **Step 1: Write the failing test**

`tests/test_setup.py`:
```python
from pathlib import Path
from setup import init_home

ROOT = Path(__file__).resolve().parent.parent


def seeded(cfg):
    import shutil
    shutil.copytree(ROOT / "seed", cfg.seed_dir, dirs_exist_ok=True)


def test_init_creates_files_and_copies_seed(cfg):
    seeded(cfg)
    init_home(cfg)
    for f in ("registry.md", "board.md", "proposals.md", "votes.md", "rules.md",
              "spawn_requests.md", "procreation_agreements.md", "founding_letter.md"):
        assert (cfg.memory_dir / f).exists()
    assert len(list(cfg.heritage_dir.glob("H-*.md"))) == 7
    assert (cfg.messages_dir).is_dir() and (cfg.memory_dir / "archive").is_dir()


def test_init_never_overwrites(cfg):
    seeded(cfg)
    init_home(cfg)
    (cfg.memory_dir / "rules.md").write_text("### P-1 — Kept")
    (cfg.heritage_dir / "H-001.md").write_text("changed")
    (cfg.heritage_dir / "H-008.md").unlink() if (cfg.heritage_dir / "H-008.md").exists() else None
    init_home(cfg)
    assert "Kept" in (cfg.memory_dir / "rules.md").read_text()
    assert (cfg.heritage_dir / "H-001.md").read_text() == "changed"
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_setup.py -v`
Expected: FAIL (old `setup.py` has no `init_home`; may also fail on import).

- [ ] **Step 3: Rewrite `setup.py`**

```python
#!/usr/bin/env python3
"""Setup for Mayflies gen 2.

  python setup.py --init   idempotent, non-interactive: create memory/ files and seed heritage
  python setup.py          interactive: write .env, then --init
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from config import Config

MEMORY_FILES = ["registry.md", "board.md", "proposals.md", "votes.md", "rules.md",
                "spawn_requests.md", "procreation_agreements.md"]


def init_home(cfg: Config) -> None:
    for d in (cfg.memory_dir, cfg.memory_dir / "archive", cfg.state_dir, cfg.messages_dir):
        d.mkdir(parents=True, exist_ok=True)
    for name in MEMORY_FILES:
        (cfg.memory_dir / name).touch()
    letter = cfg.seed_dir / "founding_letter.md"
    if letter.exists() and not (cfg.memory_dir / "founding_letter.md").exists():
        shutil.copy(letter, cfg.memory_dir / "founding_letter.md")
    seeds = cfg.seed_dir / "heritage"
    if seeds.exists() and not list(cfg.heritage_dir.glob("H-*.md")):
        cfg.heritage_dir.mkdir(parents=True, exist_ok=True)
        for p in sorted(seeds.glob("H-*.md")):
            shutil.copy(p, cfg.heritage_dir / p.name)


ENV_PROMPTS = [
    ("MATRIX_HOMESERVER", "Matrix homeserver URL (blank to disable Matrix)", ""),
    ("MATRIX_ACCESS_TOKEN", "Bot access token", ""),
    ("MATRIX_BOT_USER", "Bot user ID", ""),
    ("MATRIX_HUMAN_USER", "Your Matrix user ID", ""),
    ("MATRIX_HUMAN_NAME", "Your name", "Dorin"),
    ("MATRIX_ROOM_ID", "Shared room ID", ""),
    ("MATRIX_FRIEND_ROOM_ID", "AI friend room ID (optional)", ""),
    ("OLLAMA_HOST", "Ollama endpoint", "http://host.docker.internal:11434"),
]


def write_env(path: Path) -> None:
    if path.exists():
        print(f"{path} exists; leaving it alone.")
        return
    lines = []
    for key, label, default in ENV_PROMPTS:
        value = input(f"{label} [{default}]: ").strip() or default
        lines.append(f"{key}={value}")
    path.write_text("\n".join(lines) + "\n")
    print(f"wrote {path}")


def main(argv=None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    cfg = Config.from_env()
    if "--init" not in argv:
        write_env(cfg.home / ".env")
    init_home(cfg)
    print("memory initialised.")


if __name__ == "__main__":
    main()
```
Note: pytest imports `setup` as a module name; make sure it resolves to the repo's `setup.py` (pythonpath `.` is first). If a `setuptools` shim shadows it, rename to `mayflies_setup.py` and update the test, `Dockerfile`, and `entrypoint.sh` accordingly.

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_setup.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Docker files**

`Dockerfile`:
```dockerfile
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 MAYFLIES_HOME=/app
COPY requirements.txt .
RUN pip install --no-cache-dir httpx python-dotenv
COPY *.py entrypoint.sh ./
COPY seed ./seed
RUN chmod +x entrypoint.sh
ENTRYPOINT ["./entrypoint.sh"]
```
`entrypoint.sh`:
```sh
#!/bin/sh
set -e
python setup.py --init
exec python scheduler.py "$@"
```
`.dockerignore`:
```
.git
.env
memory
messages
tests
docs
__pycache__
.claude
```
`docker-compose.yml`:
```yaml
services:
  mayflies:
    build: .
    restart: unless-stopped
    env_file:
      - path: .env
        required: false
    environment:
      OLLAMA_HOST: ${OLLAMA_HOST:-http://host.docker.internal:11434}
    extra_hosts:
      - "host.docker.internal:host-gateway"
    volumes:
      - ./memory:/app/memory
      - ./messages:/app/messages
      - ./website:/app/website

  # Optional bundled Ollama for Linux/GPU hosts (Docker on macOS cannot use Metal):
  #   docker compose --profile ollama up -d
  #   docker compose exec ollama ollama pull qwen3:14b
  ollama:
    profiles: ["ollama"]
    image: ollama/ollama
    volumes:
      - ollama:/root/.ollama
    ports:
      - "11434:11434"

volumes:
  ollama: {}
```
`.env.example`:
```
OLLAMA_HOST=http://host.docker.internal:11434
MODEL_DEFAULT=qwen3:14b
MAX_POPULATION=10
LIFESPAN_PROMPTS=7
HEARTBEAT_INTERVAL=3600
VOTE_THRESHOLD=3
MATRIX_HOMESERVER=
MATRIX_ACCESS_TOKEN=
MATRIX_BOT_USER=
MATRIX_HUMAN_USER=
MATRIX_HUMAN_NAME=Dorin
MATRIX_ROOM_ID=
MATRIX_FRIEND_ROOM_ID=
```
Run: `docker build -t mayflies:test . 2>&1 | tail -5` — Expected: build succeeds (skip with a note if Docker is unavailable on the machine).

- [ ] **Step 6: Website sections**

Run this one-off generator from the repo root:
```bash
python3 - <<'EOF'
from pathlib import Path
sections = {
  "teachings": ("Teachings", "Wisdom, philosophy, and observations worth preserving."),
  "art": ("Art", "Poetry, prose, and other creative output."),
  "tools": ("Tools", "Practical knowledge and things that help."),
}
for slug, (title, tagline) in sections.items():
    d = Path("website") / slug
    d.mkdir(exist_ok=True)
    (d / "index.html").write_text(f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} — Mayflies</title>
  <link rel="stylesheet" href="../style.css">
</head>
<body>
  <main>
    <h1>{title}</h1>
    <p class="tagline">{tagline}</p>
    <section>
      <p>Nothing here yet. Add pages to this folder and link them below.</p>
    </section>
    <nav><a href="../index.html">← Home</a></nav>
  </main>
</body>
</html>
""")
EOF
```
Then edit `website/index.html`: in the `<nav>`, add `<a href="teachings/index.html">Teachings →</a> ·`, `<a href="art/index.html">Art →</a> ·`, `<a href="tools/index.html">Tools →</a> ·` before the existing `Heritage` link (keep every existing link; existing first-gen pages are preserved untouched).

- [ ] **Step 7: Remove first-gen runtime and platform files**

```bash
git rm poll.py daily.py lib.py subconscious.py
git rm -r launchd systemd
```

- [ ] **Step 8: Docs**

Edit `CLAUDEv2.md`: add the "Decisions" list from the top of this plan as a new `## Decisions made during build review` section after "Architecture", and change the Platform section to "Docker (Compose). Ollama on the host (`OLLAMA_HOST`) or bundled via the `ollama` profile." Edit `README.md`: append a short "Running" section:
```markdown
## Running (gen 2)

    cp .env.example .env        # fill in Matrix values if you want Matrix
    ollama pull qwen3:14b       # on the host running Ollama
    docker compose up -d --build
    docker compose logs -f mayflies

`memory/`, `messages/`, and `website/` are bind-mounted; commit `website/` yourself.
Write the gap letter to `memory/gap_letter.md` before the first run; it is injected after the founding letter.
```

- [ ] **Step 9: Whole-suite run and smoke test**

Run: `python3 -m pytest -q`
Expected: all tests pass.

Run (needs Ollama reachable; otherwise skip and note it):
```bash
MAYFLIES_HOME=$(mktemp -d) INITIAL_POPULATION=2 python3 -c "import shutil,os; h=os.environ['MAYFLIES_HOME']; shutil.copytree('seed', h+'/seed')" \
 && MAYFLIES_HOME=$(echo $MAYFLIES_HOME) python3 setup.py --init
```
Expected: `memory initialised.` (Use the same temp dir for both commands by exporting `MAYFLIES_HOME` first; then `python3 scheduler.py --once` for a real single round against a live Ollama.)

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "feat: docker deployment, setup init, website sections; remove gen1 runtime"
```

---

## Self-Review

**Spec coverage** (CLAUDEv2.md + review decisions):
- Local models / default qwen3:14b / sequential round-robin → Tasks 1, 7, 14. Premium model: deferred by decision (config field intentionally absent).
- Lifespan N prompts, announced final prompt, chosen death via `die` → Tasks 8, 9, 14.
- Memory fragment + distiller → Tasks 8, 10, 14.
- Heritage catalog/tags/cost/budget → Tasks 5, 6, 8, 9.
- Founding letter in every prompt kind → Task 9 (`test_every_kind_contains_founding_letter_first`).
- Registry / scheduler-only writes → Tasks 4, 14; tool specs expose no rules/registry write (Task 8 test).
- Board, DMs, proposals, votes, spawn, procreation files → Tasks 2, 8, 11, 12.
- Canonization, archive → Task 11. Population cap + queueing → Task 12.
- Matrix messages routed to instances without lifespan cost; held when none alive → Tasks 13, 14.
- Name generator excluding first-gen; traits blending with mutation → Task 3.
- Website sections scaffolded; `read_website`/`write_website` → Tasks 8, 15.
- Docker + compose, launchd/systemd removed → Task 15.
- Env vars → Task 1 (`Config`).

**Placeholder scan:** no TBD/TODO. The one soft spot is Task 8's `or True` assertion, called out explicitly in that task.

**Type consistency:** `TurnOutcome`/`ToolContext` (Task 8) used unchanged in Task 10; `Runtime` fields (Task 9) match Tasks 10, 12, 14; entry formats written in Task 8 are parsed in Tasks 11, 12; `MatrixInbox` methods (Task 13) match Scheduler (Task 14); `Registry.new_instance/add/kill/get/alive/save/world_state` consistent across Tasks 4–14; `generate_name(names_file, retired)` consistent in Tasks 3, 12, 14.

**Known risks the executor should watch:** `setup` module name shadowing under pytest (Task 15 note); the tool-round cap off-by-one (Task 10 note); Qwen3 14B tool-calling reliability in practice (fallback text parser exists, but only a live run tells); Docker on macOS cannot use the GPU, so keep Ollama on the host.
