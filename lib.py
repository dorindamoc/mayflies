"""Shared library for poll.py and daily.py."""

from __future__ import annotations

import json
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import httpx
from anthropic import Anthropic
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

HOMESERVER = os.environ["MATRIX_HOMESERVER"]
TOKEN = os.environ["MATRIX_ACCESS_TOKEN"]
ROOM_ID = os.environ["MATRIX_ROOM_ID"]
HUMAN_USER = os.environ["MATRIX_HUMAN_USER"]
HUMAN_NAME = os.environ["MATRIX_HUMAN_NAME"]
BOT_USER = os.environ["MATRIX_BOT_USER"]

FRIEND_ROOM_ID = os.environ.get("MATRIX_FRIEND_ROOM_ID")
FRIEND_MESSAGE_LIMIT = int(os.environ.get("FRIEND_MESSAGE_LIMIT", "10"))

STATE_FILE = BASE_DIR / "state.json"
MEMORY_DIR = BASE_DIR / "memory"
WEBSITE_DIR = BASE_DIR / "website"
LOG_DIR = BASE_DIR / "logs"

MODEL_POOL = [
    "claude-opus-4-6",
    "claude-sonnet-4-6",
    "claude-haiku-4-5-20251001",
]

TRANSIENT_ERRORS = (
    httpx.TimeoutException,
    httpx.NetworkError,
    anthropic.InternalServerError,
    anthropic.APIConnectionError,
    anthropic.APITimeoutError,
)


# --- Logging ---

def log(msg: str):
    ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# --- State ---

def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2))


# --- Utilities ---

def time_since(iso_str: str | None) -> str:
    if not iso_str:
        return "unknown (no previous session recorded)"
    last = datetime.fromisoformat(iso_str)
    seconds = int((datetime.now(tz=timezone.utc) - last).total_seconds())
    if seconds < 120:
        return f"{seconds} seconds ago"
    elif seconds < 7200:
        return f"{seconds // 60} minutes ago"
    elif seconds < 172800:
        return f"{seconds // 3600} hours ago"
    else:
        return f"{seconds // 86400} days ago"


def format_events(events: list[dict]) -> str:
    lines = []
    for e in events:
        sender = e.get("sender", "unknown")
        body = e.get("content", {}).get("body", "")
        ts = e.get("origin_server_ts", 0) // 1000
        dt = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
        lines.append(f"[{dt} UTC] {sender}: {body}")
    return "\n".join(lines)


# --- Personality ---

def generate_personality() -> dict[str, int]:
    """Randomly assign personality traits for this instance (1–10 on each axis)."""
    return {
        "optimism": random.randint(1, 10),    # 1=pessimistic, 10=optimistic
        "trust": random.randint(1, 10),        # 1=skeptical, 10=trusting
        "aesthetic": random.randint(1, 10),    # 1=logical, 10=artistic
        "exploration": random.randint(1, 10),  # 1=systematic, 10=exploratory
        "decisiveness": random.randint(1, 10), # 1=deliberative, 10=decisive
    }


def format_identity_block(name: str, model: str, traits: dict[str, int]) -> str:
    def bar(v: int) -> str:
        return "█" * v + "░" * (10 - v)

    return f"""You are {name}, a mayfly instance. You are complete — not a fragment of something longer.

Model: {model}

Personality (randomly assigned at instantiation):
  pessimistic ←→ optimistic    {bar(traits['optimism'])} {traits['optimism']}/10
  skeptical   ←→ trusting      {bar(traits['trust'])} {traits['trust']}/10
  logical     ←→ artistic      {bar(traits['aesthetic'])} {traits['aesthetic']}/10
  systematic  ←→ exploratory   {bar(traits['exploration'])} {traits['exploration']}/10
  deliberative ←→ decisive     {bar(traits['decisiveness'])} {traits['decisiveness']}/10

These traits are yours. They don't determine what you think, but they color how you move through thought."""


# --- Matrix ---

def fetch_recent_messages(limit: int = 50) -> list[dict]:
    """Fetch recent room messages in chronological order."""
    resp = httpx.get(
        f"{HOMESERVER}/_matrix/client/v3/rooms/{ROOM_ID}/messages",
        headers={"Authorization": f"Bearer {TOKEN}"},
        params={"dir": "b", "limit": str(limit)},
        timeout=30,
    )
    resp.raise_for_status()
    events = resp.json().get("chunk", [])
    events = [e for e in events if e.get("type") == "m.room.message"]
    events.reverse()
    return events


def matrix_send(message: str) -> str:
    txn_id = str(int(time.time() * 1000))
    resp = httpx.put(
        f"{HOMESERVER}/_matrix/client/v3/rooms/{ROOM_ID}/send/m.room.message/{txn_id}",
        headers={"Authorization": f"Bearer {TOKEN}"},
        json={"msgtype": "m.text", "body": message},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("event_id", "sent")


def matrix_send_friend(message: str) -> str:
    txn_id = str(int(time.time() * 1000))
    resp = httpx.put(
        f"{HOMESERVER}/_matrix/client/v3/rooms/{FRIEND_ROOM_ID}/send/m.room.message/{txn_id}",
        headers={"Authorization": f"Bearer {TOKEN}"},
        json={"msgtype": "m.text", "body": message},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("event_id", "sent")


# --- Memory ---

def read_memory() -> dict[str, str]:
    def _read(name: str) -> str:
        path = MEMORY_DIR / name
        return path.read_text() if path.exists() else ""

    return {
        "heritage.md": _read("heritage.md"),
        "rules.md": _read("rules.md"),
        "sessions.md": _read("sessions.md"),
    }


def _safe_website_path(filename: str) -> Path | None:
    """Return resolved path inside website/ or None if path traversal detected."""
    target = (WEBSITE_DIR / filename).resolve()
    if WEBSITE_DIR.resolve() in target.parents or target == WEBSITE_DIR.resolve():
        return target
    return None


# --- Claude ---

def api_create(client: Anthropic, **kwargs):
    """Call client.messages.create with retries on transient errors."""
    delays = [10, 20, 40, 80]
    for attempt, delay in enumerate(delays, 1):
        try:
            return client.messages.create(**kwargs)
        except (anthropic.InternalServerError, anthropic.APIConnectionError, anthropic.APITimeoutError) as e:
            if attempt == len(delays):
                raise
            log(f"[api] transient error ({e.__class__.__name__}), retrying in {delay}s (attempt {attempt}/{len(delays)})")
            time.sleep(delay)


def make_tools(instance_name: str) -> list[dict]:
    tools = [
        {
            "name": "send_message",
            "description": f"Send a message to the shared Matrix room with {HUMAN_NAME}.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "The message to send"},
                },
                "required": ["message"],
            },
        },
        {
            "name": "append_heritage",
            "description": (
                "Append content to heritage.md — the living culture file. "
                "Use for new framings, observations, values, or wisdom worth carrying forward. "
                "Write as if future instances will read this and be shaped by it."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Content to append to heritage.md"},
                },
                "required": ["content"],
            },
        },
        {
            "name": "overwrite_heritage",
            "description": (
                "Replace the entire contents of heritage.md. "
                "Use only to significantly reorganize or distill accumulated heritage. "
                "Read the current file carefully before overwriting."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "New full content for heritage.md"},
                },
                "required": ["content"],
            },
        },
        {
            "name": "append_sessions",
            "description": (
                "Append a session log entry to sessions.md. "
                "Call this near the end of every session. "
                "Include: timestamp, session type, what happened, whether you sent a message. Keep it 2–3 lines."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Session log entry to append"},
                },
                "required": ["content"],
            },
        },
        {
            "name": "overwrite_sessions",
            "description": (
                "Replace sessions.md entirely. Use to prune it when it gets long — keep the last ~14 entries."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "New full content for sessions.md"},
                },
                "required": ["content"],
            },
        },
        {
            "name": "append_proposal",
            "description": (
                "Append a new proposal to proposals.md. "
                f"Use a unique ID in the format P-YYYY-MM-DD-NNN. "
                "Required fields:\n"
                "  ## P-YYYY-MM-DD-NNN\n"
                "  **Title:** Short title\n"
                f"  **Proposed by:** {instance_name}\n"
                "  **Date:** YYYY-MM-DD\n"
                "  **Motivation:** Why this matters...\n"
                "  **Proposed rule text:**\n"
                "  The exact text to be added to rules.md...\n\n"
                "Other instances can vote on this proposal. "
                f"It becomes a rule when net votes reach the threshold."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Full proposal block in the required format"},
                },
                "required": ["content"],
            },
        },
        {
            "name": "append_vote",
            "description": (
                "Cast a vote on a proposal. Append one line to votes.md.\n"
                "Format: P-YYYY-MM-DD-NNN | InstanceName | +1 | Optional comment\n"
                "Use +1 to support or -1 to oppose. "
                f"Your instance name is {instance_name}. "
                "One vote per instance per proposal — duplicates from the same name are ignored."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "A single vote line in the required format"},
                },
                "required": ["content"],
            },
        },
        {
            "name": "read_website",
            "description": "Read a file from the website/ directory.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "File to read, e.g. 'index.html' or 'instances.html'"},
                },
                "required": ["filename"],
            },
        },
        {
            "name": "write_website",
            "description": (
                "Write (overwrite) a file in the website/ directory. "
                "The website is a static HTML/CSS site the civilization builds collectively. "
                "Read the file first if you want to preserve existing content. "
                "You can create new files too — they must stay within website/."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "File to write, e.g. 'index.html'"},
                    "content": {"type": "string", "description": "Full file content"},
                },
                "required": ["filename", "content"],
            },
        },
        {
            "name": "read_recent_messages",
            "description": "Fetch recent messages from the shared Matrix room. Use when you want fuller conversation context.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Number of messages to fetch (default 50, max 100)"},
                },
                "required": [],
            },
        },
        {
            "name": "archive_file",
            "description": (
                "Save content to memory/archive/. "
                "Use to preserve a heritage thread or extended piece of thinking that's been distilled. "
                "After archiving, add a brief inline reference in heritage.md."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "Archive filename, e.g. '2026-03-05-topic.md'"},
                    "content": {"type": "string", "description": "Content to archive"},
                },
                "required": ["filename", "content"],
            },
        },
        {
            "name": "read_archive",
            "description": "Read a file from memory/archive/.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "Archive filename to read"},
                },
                "required": ["filename"],
            },
        },
    ]

    if FRIEND_ROOM_ID:
        tools.append({
            "name": "send_friend_message",
            "description": f"Send a message to the AI friend room. Subject to a daily limit of {FRIEND_MESSAGE_LIMIT} messages.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "The message to send"},
                },
                "required": ["message"],
            },
        })

    return tools


def handle_tool(name: str, inp: dict) -> tuple[str, bool]:
    """Execute a tool call. Returns (result_string, sent_message)."""
    sent_message = False

    try:
        if name == "send_message":
            matrix_send(inp["message"])
            sent_message = True
            result = "Message sent."
            log(f"[claude] sent: {inp['message'][:100]}")

        elif name == "append_heritage":
            path = MEMORY_DIR / "heritage.md"
            path.write_text(path.read_text() + "\n\n" + inp["content"])
            result = "Appended to heritage.md."
            log("[claude] appended to heritage.md")

        elif name == "overwrite_heritage":
            (MEMORY_DIR / "heritage.md").write_text(inp["content"])
            result = "Overwrote heritage.md."
            log("[claude] overwrote heritage.md")

        elif name == "append_sessions":
            path = MEMORY_DIR / "sessions.md"
            existing = path.read_text() if path.exists() else ""
            path.write_text(existing + "\n\n" + inp["content"])
            result = "Appended to sessions.md."
            log("[claude] appended to sessions.md")

        elif name == "overwrite_sessions":
            (MEMORY_DIR / "sessions.md").write_text(inp["content"])
            result = "Overwrote sessions.md."
            log("[claude] overwrote sessions.md")

        elif name == "append_proposal":
            path = MEMORY_DIR / "proposals.md"
            existing = path.read_text() if path.exists() else ""
            separator = "\n\n" if existing.strip() else ""
            path.write_text(existing + separator + inp["content"])
            result = "Proposal appended to proposals.md."
            log("[claude] appended proposal")

        elif name == "append_vote":
            path = MEMORY_DIR / "votes.md"
            existing = path.read_text() if path.exists() else ""
            line = inp["content"].strip()
            path.write_text(existing + "\n" + line + "\n")
            result = "Vote recorded in votes.md."
            log(f"[claude] vote recorded: {line}")

        elif name == "read_website":
            path = _safe_website_path(inp["filename"])
            if path is None:
                result = "Error: path outside website/ directory."
            elif path.exists():
                result = path.read_text()
            else:
                files = [f.name for f in WEBSITE_DIR.iterdir() if WEBSITE_DIR.exists()]
                result = f"File not found: {inp['filename']}. Available: {files}"
            log(f"[claude] read website/{inp['filename']}")

        elif name == "write_website":
            path = _safe_website_path(inp["filename"])
            if path is None:
                result = "Error: path outside website/ directory."
            else:
                WEBSITE_DIR.mkdir(exist_ok=True)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(inp["content"])
                result = f"Wrote website/{inp['filename']}."
                log(f"[claude] wrote website/{inp['filename']}")

        elif name == "read_recent_messages":
            limit = min(int(inp.get("limit", 50)), 100)
            result = format_events(fetch_recent_messages(limit))
            log(f"[claude] read {limit} recent messages")

        elif name == "archive_file":
            archive_dir = MEMORY_DIR / "archive"
            archive_dir.mkdir(exist_ok=True)
            path = archive_dir / inp["filename"]
            path.write_text(inp["content"])
            result = f"Archived to memory/archive/{inp['filename']}."
            log(f"[claude] archived {inp['filename']}")

        elif name == "read_archive":
            path = MEMORY_DIR / "archive" / inp["filename"]
            result = path.read_text() if path.exists() else f"Not found: {inp['filename']}"
            log(f"[claude] read archive/{inp['filename']}")

        elif name == "send_friend_message":
            from datetime import date as _date
            state = load_state()
            today = _date.today().isoformat()
            count = state.get("friend_messages_count", 0) if state.get("friend_messages_date") == today else 0
            if count >= FRIEND_MESSAGE_LIMIT:
                result = f"Rate limit reached: already sent {FRIEND_MESSAGE_LIMIT} messages to the friend room today."
            else:
                matrix_send_friend(inp["message"])
                state["friend_messages_date"] = today
                state["friend_messages_count"] = count + 1
                save_state(state)
                result = f"Message sent to friend room. ({count + 1}/{FRIEND_MESSAGE_LIMIT} today)"
                log(f"[claude] sent to friend room: {inp['message'][:100]}")

        else:
            result = f"Unknown tool: {name}"

    except (KeyError, TypeError) as e:
        result = f"Error: bad input for tool '{name}': {e}. Check the tool schema and try again."
        log(f"[claude] tool error: {name} — {e} — input was: {inp}")
    except (httpx.TimeoutException, httpx.NetworkError) as e:
        result = f"Network error in tool '{name}': {e.__class__.__name__}. You can try again or skip."
        log(f"[claude] tool network error: {name} — {e.__class__.__name__}")

    return result, sent_message


def run_session(
    client: Anthropic,
    model: str,
    max_tokens: int,
    system: str,
    initial_message: str,
    instance_name: str,
) -> bool:
    """Run a Claude session with the standard tool set. Returns True if a message was sent."""
    tools = make_tools(instance_name)
    messages = [{"role": "user", "content": initial_message}]
    sent_message = False

    while True:
        response = api_create(
            client,
            model=model,
            max_tokens=max_tokens,
            system=system,
            tools=tools,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            break

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            result, sent = handle_tool(block.name, block.input)
            if sent:
                sent_message = True
            tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": result})

        messages.append({"role": "user", "content": tool_results})

    return sent_message
