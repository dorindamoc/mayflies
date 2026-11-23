"""Matrix plumbing: send to the rooms, fetch Dorin's messages, track delivery."""

from __future__ import annotations

import json
import re
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


def addressed_names(body: str, alive_names: list) -> list:
    """Living instances a message names as "for <name>" (any case or spacing), in order of appearance."""
    found = []
    for name in alive_names:
        pattern = r"(?<!\w)for\s+" + r"\s+".join(re.escape(part) for part in name.split()) + r"(?!\w)"
        m = re.search(pattern, body, re.IGNORECASE)
        if m:
            found.append((m.start(), name))
    return [name for _, name in sorted(found)]


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

    def due(self, receiving_names: list, alive_names: list = None) -> list:
        """Deliveries owed now. A message goes to the receiving instances, or, when it names living instances
        with "for <name>", only to those of them that are receiving (so a named newborn is not written to)."""
        alive_names = receiving_names if alive_names is None else alive_names
        out = []
        for p in self.pending:
            if p["targets"] is None:
                named = addressed_names(p["body"], alive_names)
                if named:
                    p["targets"] = [n for n in named if n in receiving_names]
                elif receiving_names:
                    p["targets"] = list(receiving_names)
                else:
                    continue
            for name in p["targets"]:
                if name not in p["delivered"] and name in receiving_names:
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
