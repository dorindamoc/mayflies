"""Each instance's two memory files: short-term (last prompt) and long-term (everything before it)."""

from __future__ import annotations

from budget import est_tokens
from config import Config
from store import atomic_write

NOTE_LABEL = "I wanted to remember:"


class Memories:
    def __init__(self, cfg: Config):
        self.cfg = cfg

    def _file(self, name: str, which: str):
        return self.cfg.memories_dir / name / f"{which}.md"

    def _read(self, name: str, which: str) -> str:
        path = self._file(name, which)
        return path.read_text().strip() if path.exists() else ""

    def _write(self, name: str, which: str, text: str) -> None:
        atomic_write(self._file(name, which), text)

    # --- short term: a recap of the last prompt, and the note the instance chose to keep ---
    def short(self, name: str) -> tuple:
        text = self._read(name, "short_term")
        recap, _, note = text.partition(f"\n\n{NOTE_LABEL}")
        if not recap.startswith(NOTE_LABEL):
            return recap.strip(), note.strip()
        return "", recap[len(NOTE_LABEL):].strip()

    def short_text(self, name: str) -> str:
        return self._read(name, "short_term")

    def set_short(self, name: str, recap: str, note: str = "") -> None:
        recap, note = recap.strip(), note.strip()
        self._write(name, "short_term", f"{recap}\n\n{NOTE_LABEL} {note}" if note else recap)

    # --- long term: compacted entries, one per earlier prompt ---
    def long(self, name: str) -> str:
        return self._read(name, "long_term")

    def append_long(self, name: str, entry: str) -> None:
        old = self.long(name)
        self._write(name, "long_term", f"{old}\n- {entry.strip()}" if old else f"- {entry.strip()}")

    def fill(self, name: str) -> float:
        text = self.long(name)
        return est_tokens(text) / self.cfg.long_term_tokens if text else 0.0

    def is_full(self, name: str) -> bool:
        return self.fill(name) >= 1
