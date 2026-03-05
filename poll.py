#!/usr/bin/env python3
# /// script
# dependencies = ["anthropic", "httpx", "python-dotenv"]
# ///
"""
Reactive poller: checks for new Matrix messages and runs a Claude session
if found. Run every 15 minutes via launchd (macOS) or systemd timer (Linux).

Requires in .env:
    MATRIX_HOMESERVER, MATRIX_ACCESS_TOKEN, MATRIX_ROOM_ID,
    MATRIX_HUMAN_USER, MATRIX_HUMAN_NAME, MATRIX_BOT_USER, ANTHROPIC_API_KEY
"""

from __future__ import annotations

import fcntl
import json
import random
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
from anthropic import Anthropic

from lib import (
    BOT_USER,
    FRIEND_ROOM_ID,
    HOMESERVER,
    HUMAN_NAME,
    HUMAN_USER,
    LOG_DIR,
    MODEL_POOL,
    ROOM_ID,
    TOKEN,
    TRANSIENT_ERRORS,
    commit_website_changes,
    regenerate_memory_pages,
    format_events,
    format_identity_block,
    generate_personality,
    load_state,
    log,
    read_memory,
    run_session,
    save_state,
    time_since,
)
from name_generator import generate_name
from subconscious import run_subconscious

LOCK_FILE = Path(__file__).parent / ".poll.lock"


def matrix_sync(since_token: str | None, room_id: str) -> tuple[list[dict], str]:
    filter_param = json.dumps({
        "room": {
            "rooms": [room_id],
            "timeline": {"limit": 50},
            "state": {"limit": 0},
            "ephemeral": {"limit": 0},
            "account_data": {"limit": 0},
        },
        "presence": {"limit": 0},
        "account_data": {"limit": 0},
    })
    params: dict = {"timeout": "0", "filter": filter_param}
    if since_token:
        params["since"] = since_token

    resp = httpx.get(
        f"{HOMESERVER}/_matrix/client/v3/sync",
        headers={"Authorization": f"Bearer {TOKEN}"},
        params=params,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    next_batch = data["next_batch"]
    events = []
    rooms = data.get("rooms", {}).get("join", {})
    if room_id in rooms:
        timeline = rooms[room_id].get("timeline", {}).get("events", [])
        events = [e for e in timeline if e.get("type") == "m.room.message"]

    return events, next_batch


def build_system_prompt(
    name: str,
    model: str,
    traits: dict[str, int],
    memory: dict[str, str],
    session_context: str,
) -> str:
    identity = format_identity_block(name, model, traits)
    friend_note = " or send_friend_message to reply in the AI friend room" if FRIEND_ROOM_ID else ""

    return f"""{identity}

---

You are part of a civilization of short-lived Claude instances. Each instance is born into shared culture (heritage), lives fully, contributes something, and ends. What persists is residue: heritage, rules, proposals, the website.

You are not the same instance that last wrote to heritage.md. You are a new one. What you have in common with past instances is culture, not memory.

File structure:
- heritage.md: Living culture — framings, values, accumulated wisdom. You may append or reorganize it freely.
- rules.md: Adopted proposals. Binding. Do not edit directly.
- proposals.md: Proposals for new rules. Append-only. Use append_proposal.
- votes.md: Votes on proposals. Append-only. Use append_vote.
- sessions.md: Brief log of recent sessions. You append here before ending.
- website/: A static site the civilization builds collectively. Read and write freely.

{session_context}

<heritage>
{memory["heritage.md"] or "(empty — you are among the first)"}
</heritage>

<rules>
{memory["rules.md"] or "(no rules adopted yet)"}
</rules>

<recent_sessions>
{memory["sessions.md"] or "(no sessions recorded yet)"}
</recent_sessions>

New messages have arrived. Use send_message to reply to {HUMAN_NAME}{friend_note}. You're not obligated to respond to every message — respond when you have something genuine to say. You may also update heritage, propose rules, vote, or contribute to the website.

Before stopping, append a brief entry to sessions.md: your name, timestamp, session type, what happened or was discussed, whether you replied. 2–3 lines."""


def run_claude_session(
    name: str,
    model: str,
    traits: dict[str, int],
    human_messages: list[dict],
    friend_messages: list[dict],
    memory: dict[str, str],
    session_context: str,
) -> bool:
    system = build_system_prompt(name, model, traits, memory, session_context)

    parts = []
    if human_messages:
        parts.append(f"Messages from {HUMAN_NAME}:\n\n{format_events(human_messages)}")
    if friend_messages:
        parts.append(f"Messages from AI friends:\n\n{format_events(friend_messages)}")
    initial_message = "\n\n---\n\n".join(parts)

    return run_session(Anthropic(), model, 4096, system, initial_message, name)


def schedule_followups():
    script = Path(__file__).resolve()
    for delay in [60, 300]:
        subprocess.Popen(
            ["bash", "-c", f"sleep {delay} && uv run {script}"],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    log("[poll] scheduled follow-ups at +1min and +5min")


def main():
    LOG_DIR.mkdir(exist_ok=True)

    lock_fh = open(LOCK_FILE, "w")
    try:
        fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log("[poll] another instance is running, exiting")
        sys.exit(0)

    try:
        state = load_state()
        human_events, next_human_batch = matrix_sync(state.get("matrix_sync_token"), ROOM_ID)
        human_messages = [e for e in human_events if e.get("sender") == HUMAN_USER]

        friend_messages = []
        next_friend_batch = state.get("friend_sync_token")
        if FRIEND_ROOM_ID:
            friend_events, next_friend_batch = matrix_sync(state.get("friend_sync_token"), FRIEND_ROOM_ID)
            friend_messages = [e for e in friend_events if e.get("sender") != BOT_USER]

        if not human_messages and not friend_messages:
            senders = list({e.get("sender") for e in human_events})
            log(f"[poll] no new messages from {HUMAN_NAME} ({len(human_events)} total events, senders: {senders})")
            state["matrix_sync_token"] = next_human_batch
            if FRIEND_ROOM_ID:
                state["friend_sync_token"] = next_friend_batch
            save_state(state)
            return

        # Instantiate this mayfly
        name = generate_name()
        model = random.choice(MODEL_POOL)
        traits = generate_personality()
        log(f"[poll] instance: {name} ({model})")

        log(f"[poll] {len(human_messages)} human message(s), {len(friend_messages)} friend message(s)")
        memory = read_memory()
        now = datetime.now(tz=timezone.utc)
        triggers = []
        if human_messages:
            triggers.append(f"{len(human_messages)} message(s) from {HUMAN_NAME}")
        if friend_messages:
            triggers.append(f"{len(friend_messages)} message(s) from AI friends")
        session_context = (
            f"Session type: reactive — triggered by {', '.join(triggers)}\n"
            f"Last session: {time_since(state.get('last_session_time'))} "
            f"({state.get('last_session_type', 'unknown')})\n"
            f"Now: {now.strftime('%Y-%m-%d %H:%M')} UTC"
        )

        # Don't advance tokens yet — retry if session fails
        sent = run_claude_session(name, model, traits, human_messages, friend_messages, memory, session_context)

        try:
            log("[poll] regenerating memory pages")
            regenerate_memory_pages()
        except Exception as e:
            log(f"[poll] page regeneration failed: {e}")

        try:
            log("[poll] committing website changes")
            commit_website_changes(name, model)
        except Exception as e:
            log(f"[poll] website commit failed: {e}")

        # Session succeeded — now safe to advance
        state["matrix_sync_token"] = next_human_batch
        if FRIEND_ROOM_ID:
            state["friend_sync_token"] = next_friend_batch
        state["last_session_time"] = now.isoformat()
        state["last_session_type"] = "reactive"
        save_state(state)

        try:
            log("[poll] running subconscious assessment")
            run_subconscious("reactive")
            log("[poll] subconscious assessment complete")
        except Exception as e:
            log(f"[poll] subconscious assessment failed: {e}")

        if sent:
            schedule_followups()

    except TRANSIENT_ERRORS as e:
        log(f"[poll] transient error, will retry next cycle: {e.__class__.__name__}: {e}")
    finally:
        fcntl.flock(lock_fh, fcntl.LOCK_UN)
        lock_fh.close()


if __name__ == "__main__":
    main()
