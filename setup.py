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
