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


def test_fetch_asks_server_to_filter_to_human_messages(tmp_path):
    import json as _json
    seen = {}

    def handler(req):
        seen.update(dict(req.url.params))
        return httpx.Response(200, json={"chunk": []})

    MatrixClient(mcfg(tmp_path), transport=httpx.MockTransport(handler)).fetch_human_messages()
    f = _json.loads(seen["filter"])
    assert f["senders"] == ["@d:example"] and f["types"] == ["m.room.message"]
