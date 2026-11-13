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
