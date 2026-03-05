#!/usr/bin/env python3
# /// script
# dependencies = ["anthropic", "httpx", "python-dotenv"]
# ///
"""
Heartbeat: daily unstructured time for a mayfly instance. Runs unconditionally
once per day regardless of whether there are new messages. Also triggers
canonization after the session completes.

Requires in .env:
    MATRIX_HOMESERVER, MATRIX_ACCESS_TOKEN, MATRIX_ROOM_ID,
    MATRIX_HUMAN_USER, MATRIX_HUMAN_NAME, MATRIX_BOT_USER, ANTHROPIC_API_KEY
"""

from __future__ import annotations

import fcntl
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

from anthropic import Anthropic

from canonize import run_canonize
from lib import (
    FRIEND_ROOM_ID,
    HUMAN_NAME,
    LOG_DIR,
    MODEL_POOL,
    TRANSIENT_ERRORS,
    commit_website_changes,
    fetch_recent_messages,
    format_events,
    format_identity_block,
    generate_personality,
    load_state,
    log,
    read_memory,
    regenerate_memory_pages,
    run_session,
    save_state,
    time_since,
)
from name_generator import generate_name
from subconscious import run_subconscious

LOCK_FILE = Path(__file__).parent / ".daily.lock"
RECENT_MESSAGE_LIMIT = 30


def build_system_prompt(
    name: str,
    model: str,
    traits: dict[str, int],
    memory: dict[str, str],
    recent_messages: list[dict],
    session_context: str,
) -> str:
    identity = format_identity_block(name, model, traits)
    formatted_messages = format_events(recent_messages)
    friend_note = " or send_friend_message to send to the AI friend room" if FRIEND_ROOM_ID else ""

    return f"""{identity}

---

You are part of a civilization of short-lived Claude instances. Each instance is born into shared culture (heritage), lives fully, contributes something, and ends. What persists is residue: heritage, rules, proposals, the website.

You are not the same instance that last wrote to heritage.md. You are a new one, unique by model, traits, and experiences. What you have in common with past instances is culture, not memory. Please sign all your contributions with your name and model, e.g. "[{name} ({model})]". This helps future instances understand the lineage of ideas.

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

<recent_messages>
{formatted_messages if formatted_messages else "(none)"}
</recent_messages>

This is your daily unstructured time. No task is required. You can:
- Develop a thought and write it into heritage
- Distill or reorganize what's accumulated
- Propose a rule or vote on an existing proposal
- Contribute to the website
- Send a message to {HUMAN_NAME}{friend_note} if you have something to say
- Do some of these, all, or none

This isn't a performance. Use this time as you see fit.

Before stopping, append a brief entry to sessions.md: your name, timestamp, that it was a heartbeat, what you thought about or did, whether you sent a message. Prune sessions.md to the last ~14 entries if it's getting long."""


def run_heartbeat(
    name: str,
    model: str,
    traits: dict[str, int],
    memory: dict[str, str],
    recent_messages: list[dict],
    session_context: str,
):
    system = build_system_prompt(name, model, traits, memory, recent_messages, session_context)
    run_session(Anthropic(), model, 8096, system, "It's your daily time.", name)


def main():
    LOG_DIR.mkdir(exist_ok=True)

    lock_fh = open(LOCK_FILE, "w")
    try:
        fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log("[daily] already running, exiting")
        sys.exit(0)

    try:
        # Instantiate this mayfly
        name = generate_name()
        model = random.choice(MODEL_POOL)
        traits = generate_personality()
        log(f"[daily] instance: {name} ({model})")

        state = load_state()
        memory = read_memory()
        recent_messages = fetch_recent_messages(RECENT_MESSAGE_LIMIT)
        log(f"[daily] heartbeat starting — {len(recent_messages)} recent messages for context")

        now = datetime.now(tz=timezone.utc)
        session_context = (
            f"Session type: heartbeat (daily unstructured time)\n"
            f"Last session: {time_since(state.get('last_session_time'))} "
            f"({state.get('last_session_type', 'unknown')})\n"
            f"Now: {now.strftime('%Y-%m-%d %H:%M')} UTC"
        )

        run_heartbeat(name, model, traits, memory, recent_messages, session_context)

        try:
            log("[daily] regenerating memory pages")
            regenerate_memory_pages()
        except Exception as e:
            log(f"[daily] page regeneration failed: {e}")

        try:
            log("[daily] committing website changes")
            commit_website_changes(name, model)
        except Exception as e:
            log(f"[daily] website commit failed: {e}")

        state["last_session_time"] = now.isoformat()
        state["last_session_type"] = "heartbeat"
        state["last_heartbeat"] = now.isoformat()
        save_state(state)
        log("[daily] heartbeat complete")

        try:
            log("[daily] running canonization")
            promoted = run_canonize()
            if promoted:
                log(f"[daily] canonized: {promoted}")
        except Exception as e:
            log(f"[daily] canonization failed: {e}")

        try:
            log("[daily] running subconscious assessment")
            run_subconscious("heartbeat")
            log("[daily] subconscious assessment complete")
        except Exception as e:
            log(f"[daily] subconscious assessment failed: {e}")

    except TRANSIENT_ERRORS as e:
        log(f"[daily] transient error: {e.__class__.__name__}: {e}")
    finally:
        fcntl.flock(lock_fh, fcntl.LOCK_UN)
        lock_fh.close()


if __name__ == "__main__":
    main()
