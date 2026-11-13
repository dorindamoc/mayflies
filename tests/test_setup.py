import shutil
from pathlib import Path
from setup import init_home

ROOT = Path(__file__).resolve().parent.parent


def seeded(cfg):
    shutil.copytree(ROOT / "seed", cfg.seed_dir, dirs_exist_ok=True)


def test_init_creates_files_and_copies_seed(cfg):
    seeded(cfg)
    init_home(cfg)
    for f in ("registry.md", "board.md", "proposals.md", "votes.md", "rules.md",
              "spawn_requests.md", "procreation_agreements.md", "founding_letter.md"):
        assert (cfg.memory_dir / f).exists()
    assert len(list(cfg.heritage_dir.glob("H-*.md"))) == 7
    assert cfg.messages_dir.is_dir() and (cfg.memory_dir / "archive").is_dir()


def test_init_never_overwrites(cfg):
    seeded(cfg)
    init_home(cfg)
    (cfg.memory_dir / "rules.md").write_text("### P-1 — Kept")
    (cfg.heritage_dir / "H-001.md").write_text("changed")
    init_home(cfg)
    assert "Kept" in (cfg.memory_dir / "rules.md").read_text()
    assert (cfg.heritage_dir / "H-001.md").read_text() == "changed"
