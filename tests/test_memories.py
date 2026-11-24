from memories import Memories


def test_a_new_instance_has_no_memories(cfg):
    m = Memories(cfg)
    assert m.short("Pale Rest") == ("", "") and m.long("Pale Rest") == ""
    assert m.short_text("Pale Rest") == ""


def test_short_term_keeps_recap_and_note_apart_and_lives_in_a_file(cfg):
    m = Memories(cfg)
    m.set_short("Pale Rest", "I read the lexicon.", "Keep asking what changes the archive.")
    assert Memories(cfg).short("Pale Rest") == ("I read the lexicon.", "Keep asking what changes the archive.")
    assert (cfg.memories_dir / "Pale Rest" / "short_term.md").exists()
    m.set_short("Pale Rest", "Only a recap.", "")
    assert m.short("Pale Rest") == ("Only a recap.", "")


def test_short_text_labels_the_voluntary_note(cfg):
    m = Memories(cfg)
    m.set_short("Pale Rest", "I read.", "remember the river")
    assert m.short_text("Pale Rest") == "I read.\n\nI wanted to remember: remember the river"


def test_long_term_is_appended_entry_by_entry_in_a_file(cfg):
    m = Memories(cfg)
    m.append_long("Pale Rest", "first")
    m.append_long("Pale Rest", "second")
    assert Memories(cfg).long("Pale Rest") == "- first\n- second"
    assert (cfg.memories_dir / "Pale Rest" / "long_term.md").exists()


def test_long_term_fills_towards_its_token_budget(cfg):
    m = Memories(cfg)
    assert m.fill("Pale Rest") == 0 and not m.is_full("Pale Rest")
    m.append_long("Pale Rest", "x" * (cfg.long_term_tokens * 4 // 2))
    assert 0.45 < m.fill("Pale Rest") < 0.55 and not m.is_full("Pale Rest")
    m.append_long("Pale Rest", "x" * (cfg.long_term_tokens * 4))
    assert m.is_full("Pale Rest")


def test_memory_files_are_written_atomically(cfg):
    m = Memories(cfg)
    m.set_short("Pale Rest", "recap", "note")
    m.append_long("Pale Rest", "entry")
    assert sorted(f.name for f in (cfg.memories_dir / "Pale Rest").iterdir()) == ["long_term.md", "short_term.md"]
