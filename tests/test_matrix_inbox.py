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
