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
