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
