import json

from matrix import MatrixInbox, is_urgent


def msg(i, body="hi"):
    return {"event_id": f"${i}", "body": body, "ts": i}


def fresh(tmp_path, *bodies, receiving=("A", "B")):
    inbox = MatrixInbox(tmp_path / "m.json")
    inbox.ingest([])  # baseline
    inbox.ingest([msg(i, b) for i, b in enumerate(bodies, 1)])
    inbox.resolve(list(receiving))
    return inbox


def test_first_ingest_is_baseline_not_delivered(tmp_path):
    inbox = MatrixInbox(tmp_path / "m.json")
    inbox.ingest([msg(1), msg(2)])
    inbox.resolve(["A", "B"])
    assert inbox.owed("A") == [] and inbox.immediate(["A", "B"]) == []


def test_a_message_is_owed_to_every_receiving_instance_until_delivered(tmp_path):
    inbox = fresh(tmp_path, "hello")
    assert [p["body"] for p in inbox.owed("A")] == ["hello"] and [p["body"] for p in inbox.owed("B")] == ["hello"]
    inbox.mark_delivered("$1", "A")
    assert inbox.owed("A") == [] and len(inbox.owed("B")) == 1
    inbox.mark_delivered("$1", "B")
    inbox.prune(["A", "B"])
    assert inbox.owed("A") == [] and inbox.owed("B") == [] and inbox.pending == []


def test_an_ordinary_message_waits_for_the_heartbeat(tmp_path):
    inbox = fresh(tmp_path, "hello everyone")
    assert inbox.immediate(["A", "B"]) == []
    assert len(inbox.owed("A")) == 1


def test_urgent_and_named_messages_get_a_prompt_of_their_own(tmp_path):
    assert is_urgent("Urgent: stop") and is_urgent("  URGENT - now") and not is_urgent("not urgent") and not is_urgent("urgently")
    inbox = fresh(tmp_path, "urgent: everyone")
    assert [n for n, _ in inbox.immediate(["A", "B"])] == ["A", "B"]
    named = fresh(tmp_path / "n", "for B: a word")
    assert [n for n, _ in named.immediate(["A", "B"])] == ["B"]


def test_everything_an_instance_is_owed_comes_in_one_batch(tmp_path):
    inbox = fresh(tmp_path, "quiet note", "urgent: now", "another note")
    batches = dict(inbox.immediate(["A", "B"]))
    assert [p["body"] for p in batches["A"]] == ["quiet note", "urgent: now", "another note"]
    inbox.mark_delivered("$1", "A")
    assert [p["body"] for p in dict(inbox.immediate(["A", "B"]))["A"]] == ["urgent: now", "another note"]


def test_messages_written_before_the_split_are_told_apart_when_read(tmp_path):
    (tmp_path / "m.json").write_text(json.dumps({"seen": ["$1", "$2"], "pending": [
        {"event_id": "$1", "body": "an old broadcast", "ts": 1, "targets": ["A"], "delivered": []},
        {"event_id": "$2", "body": "for A: old and named", "ts": 2, "targets": ["A"], "delivered": []}]}))
    inbox = MatrixInbox(tmp_path / "m.json")
    assert [p["body"] for p in dict(inbox.immediate(["A"]))["A"]] == ["an old broadcast", "for A: old and named"]
    only_broadcast = MatrixInbox(tmp_path / "m.json")
    only_broadcast.mark_delivered("$2", "A")
    assert only_broadcast.immediate(["A"]) == []


def test_message_waits_when_nobody_alive_and_targets_first_alive_set(tmp_path):
    inbox = MatrixInbox(tmp_path / "m.json")
    inbox.ingest([])
    inbox.ingest([msg(1, "anyone?")])
    inbox.resolve([])
    assert inbox.owed("X") == []
    inbox.resolve(["X"])
    assert len(inbox.owed("X")) == 1
    # later-born instances are not retroactive targets once the set was snapshotted
    inbox.resolve(["X", "Y"])
    assert len(inbox.owed("X")) == 1 and inbox.owed("Y") == []


def test_dead_targets_are_pruned(tmp_path):
    inbox = fresh(tmp_path, "hi")
    inbox.mark_delivered("$1", "A")
    inbox.prune(["A"])  # B died
    assert inbox.pending == []


def test_state_survives_restart_and_never_redelivers(tmp_path):
    p = tmp_path / "m.json"
    inbox = MatrixInbox(p)
    inbox.ingest([])
    inbox.ingest([msg(1)])
    inbox.resolve(["A"])
    inbox.mark_delivered("$1", "A")
    inbox.prune(["A"])
    again = MatrixInbox(p)
    again.ingest([msg(1)])  # same event seen again in the room history
    again.resolve(["A"])
    assert again.owed("A") == []
