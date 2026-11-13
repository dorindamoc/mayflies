"""Matrix plumbing: send to the rooms, fetch Dorin's messages, track delivery."""

from __future__ import annotations

import json
import time
from pathlib import Path

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
                              params={"dir": "b", "limit": str(limit), "filter": json.dumps(
                                  {"types": ["m.room.message"], "senders": [self.cfg.matrix_human_user]})})
        resp.raise_for_status()
        out = []
        for e in resp.json().get("chunk", []):
            if e.get("type") == "m.room.message" and e.get("sender") == self.cfg.matrix_human_user:
                out.append({"event_id": e["event_id"], "body": e.get("content", {}).get("body", ""),
                            "ts": e.get("origin_server_ts", 0)})
        out.reverse()
        return out


class MatrixInbox:
    """Tracks Dorin's messages and who has received them. State persists in a JSON file."""

    MAX_SEEN = 500

    def __init__(self, path: Path):
        self.path = Path(path)
        self._fresh = not self.path.exists()
        state = json.loads(self.path.read_text()) if not self._fresh else {"seen": [], "pending": []}
        self.seen: list = state["seen"]
        self.pending: list = state["pending"]

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.seen = self.seen[-self.MAX_SEEN:]
        self.path.write_text(json.dumps({"seen": self.seen, "pending": self.pending}))

    def ingest(self, messages: list) -> None:
        baseline = self._fresh
        for m in messages:
            if m["event_id"] in self.seen:
                continue
            self.seen.append(m["event_id"])
            if not baseline:
                self.pending.append({**m, "targets": None, "delivered": []})
        self._fresh = False
        self._save()

    def due(self, alive_names: list) -> list:
        out = []
        for p in self.pending:
            if p["targets"] is None:
                if not alive_names:
                    continue
                p["targets"] = list(alive_names)
            for name in p["targets"]:
                if name not in p["delivered"] and name in alive_names:
                    out.append((p, name))
        self._save()
        return out

    def mark_delivered(self, event_id: str, name: str) -> None:
        for p in self.pending:
            if p["event_id"] == event_id and name not in p["delivered"]:
                p["delivered"].append(name)
        self._save()

    def prune(self, alive_names: list) -> None:
        self.pending = [
            p for p in self.pending
            if p["targets"] is None
            or any(n not in p["delivered"] and n in alive_names for n in p["targets"])
        ]
        self._save()
