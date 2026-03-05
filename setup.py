#!/usr/bin/env python3
"""
Interactive setup for Mayflies.

Creates:
  - .env file with credentials
  - memory/ files if absent
  - Scheduler config (launchd on macOS, systemd on Linux)
"""

from __future__ import annotations

import os
import platform
import shutil
import stat
import sys
from pathlib import Path
from textwrap import dedent

BASE_DIR = Path(__file__).resolve().parent
MEMORY_DIR = BASE_DIR / "memory"
WEBSITE_DIR = BASE_DIR / "website"

# Memory files that must exist (empty if new)
MEMORY_FILES = ["heritage.md", "rules.md", "proposals.md", "votes.md", "sessions.md"]


def prompt(question: str, default: str = "", secret: bool = False) -> str:
    if default:
        display = f"{question} [{default}]: "
    else:
        display = f"{question}: "

    while True:
        if secret:
            import getpass
            value = getpass.getpass(display).strip()
        else:
            value = input(display).strip()

        if value:
            return value
        if default:
            return default
        print("  (required — please enter a value)")


def prompt_optional(question: str, hint: str = "") -> str:
    display = f"{question}"
    if hint:
        display += f" ({hint})"
    display += " [leave blank to skip]: "
    return input(display).strip()


def yn(question: str, default: bool = True) -> bool:
    suffix = " [Y/n]: " if default else " [y/N]: "
    answer = input(question + suffix).strip().lower()
    if not answer:
        return default
    return answer.startswith("y")


def write_env(values: dict[str, str]):
    env_path = BASE_DIR / ".env"
    lines = []
    for key, val in values.items():
        if val:
            lines.append(f"{key}={val}")
        else:
            lines.append(f"# {key}=")
    env_path.write_text("\n".join(lines) + "\n")
    print(f"\n  Written: {env_path}")


def init_memory():
    MEMORY_DIR.mkdir(exist_ok=True)
    (MEMORY_DIR / "archive").mkdir(exist_ok=True)
    WEBSITE_DIR.mkdir(exist_ok=True)

    for name in MEMORY_FILES:
        path = MEMORY_DIR / name
        if not path.exists():
            path.touch()
            print(f"  Created: {path.relative_to(BASE_DIR)}")
        else:
            print(f"  Exists:  {path.relative_to(BASE_DIR)}")

    # Seed heritage.md from the repo copy if memory is still empty
    heritage_path = MEMORY_DIR / "heritage.md"
    if heritage_path.stat().st_size == 0:
        repo_heritage = BASE_DIR / "memory" / "heritage.md"
        if repo_heritage.exists() and repo_heritage != heritage_path:
            shutil.copy(repo_heritage, heritage_path)
            print("  Seeded heritage.md from repo copy")


# --- macOS launchd ---

POLL_PLIST_ID = "com.mayflies.poll"
DAILY_PLIST_ID = "com.mayflies.daily"


def write_launchd_plists(uv_path: str):
    agents_dir = Path.home() / "Library" / "LaunchAgents"
    agents_dir.mkdir(parents=True, exist_ok=True)

    log_dir = BASE_DIR / "logs"
    log_dir.mkdir(exist_ok=True)

    poll_plist = agents_dir / f"{POLL_PLIST_ID}.plist"
    daily_plist = agents_dir / f"{DAILY_PLIST_ID}.plist"

    poll_plist.write_text(dedent(f"""\
        <?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
            "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
        <plist version="1.0">
        <dict>
            <key>Label</key>
            <string>{POLL_PLIST_ID}</string>
            <key>ProgramArguments</key>
            <array>
                <string>{uv_path}</string>
                <string>run</string>
                <string>{BASE_DIR / "poll.py"}</string>
            </array>
            <key>StartInterval</key>
            <integer>900</integer>
            <key>StandardOutPath</key>
            <string>{log_dir / "poll.log"}</string>
            <key>StandardErrorPath</key>
            <string>{log_dir / "poll.err"}</string>
            <key>RunAtLoad</key>
            <false/>
            <key>EnvironmentVariables</key>
            <dict>
                <key>PATH</key>
                <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
            </dict>
        </dict>
        </plist>
    """))

    daily_plist.write_text(dedent(f"""\
        <?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
            "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
        <plist version="1.0">
        <dict>
            <key>Label</key>
            <string>{DAILY_PLIST_ID}</string>
            <key>ProgramArguments</key>
            <array>
                <string>{uv_path}</string>
                <string>run</string>
                <string>{BASE_DIR / "daily.py"}</string>
            </array>
            <key>StartCalendarInterval</key>
            <dict>
                <key>Hour</key>
                <integer>9</integer>
                <key>Minute</key>
                <integer>0</integer>
            </dict>
            <key>StandardOutPath</key>
            <string>{log_dir / "daily.log"}</string>
            <key>StandardErrorPath</key>
            <string>{log_dir / "daily.err"}</string>
            <key>RunAtLoad</key>
            <false/>
            <key>EnvironmentVariables</key>
            <dict>
                <key>PATH</key>
                <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
            </dict>
        </dict>
        </plist>
    """))

    print(f"\n  Written: {poll_plist}")
    print(f"  Written: {daily_plist}")
    print("""
  To load now:
    launchctl load ~/Library/LaunchAgents/com.mayflies.poll.plist
    launchctl load ~/Library/LaunchAgents/com.mayflies.daily.plist

  To unload:
    launchctl unload ~/Library/LaunchAgents/com.mayflies.poll.plist
    launchctl unload ~/Library/LaunchAgents/com.mayflies.daily.plist
""")


# --- Linux systemd ---

def write_systemd_units(uv_path: str):
    systemd_dir = Path.home() / ".config" / "systemd" / "user"
    systemd_dir.mkdir(parents=True, exist_ok=True)

    log_dir = BASE_DIR / "logs"
    log_dir.mkdir(exist_ok=True)

    # poll: service + timer
    (systemd_dir / "mayflies-poll.service").write_text(dedent(f"""\
        [Unit]
        Description=Mayflies reactive poller
        After=network-online.target
        Wants=network-online.target

        [Service]
        Type=oneshot
        ExecStart={uv_path} run {BASE_DIR / "poll.py"}
        WorkingDirectory={BASE_DIR}
        StandardOutput=append:{log_dir / "poll.log"}
        StandardError=append:{log_dir / "poll.err"}

        [Install]
        WantedBy=default.target
    """))

    (systemd_dir / "mayflies-poll.timer").write_text(dedent("""\
        [Unit]
        Description=Mayflies reactive poller — every 15 minutes

        [Timer]
        OnBootSec=2min
        OnUnitActiveSec=15min
        Persistent=true

        [Install]
        WantedBy=timers.target
    """))

    # daily: service + timer
    (systemd_dir / "mayflies-daily.service").write_text(dedent(f"""\
        [Unit]
        Description=Mayflies daily heartbeat
        After=network-online.target
        Wants=network-online.target

        [Service]
        Type=oneshot
        ExecStart={uv_path} run {BASE_DIR / "daily.py"}
        WorkingDirectory={BASE_DIR}
        StandardOutput=append:{log_dir / "daily.log"}
        StandardError=append:{log_dir / "daily.err"}

        [Install]
        WantedBy=default.target
    """))

    (systemd_dir / "mayflies-daily.timer").write_text(dedent("""\
        [Unit]
        Description=Mayflies daily heartbeat — once per day at 09:00

        [Timer]
        OnCalendar=*-*-* 09:00:00
        Persistent=true

        [Install]
        WantedBy=timers.target
    """))

    print(f"\n  Written: {systemd_dir}/mayflies-poll.{{service,timer}}")
    print(f"  Written: {systemd_dir}/mayflies-daily.{{service,timer}}")
    print("""
  To enable and start:
    systemctl --user daemon-reload
    systemctl --user enable --now mayflies-poll.timer
    systemctl --user enable --now mayflies-daily.timer

  To check status:
    systemctl --user status mayflies-poll.timer
    journalctl --user -u mayflies-poll.service -f
""")


def main():
    print("\n=== Mayflies setup ===\n")

    # --- Matrix ---
    print("Matrix credentials")
    print("-" * 40)
    homeserver = prompt("Homeserver URL", "https://matrix.org")
    token = prompt("Bot access token", secret=True)
    bot_user = prompt("Bot Matrix user ID (e.g. @mayflies:matrix.org)")
    human_user = prompt("Founder Matrix user ID (e.g. @you:matrix.org)")
    human_name = prompt("Founder display name (e.g. Dorin)")
    room_id = prompt("Shared room ID (e.g. !abc123:matrix.org)")
    friend_room_id = prompt_optional("AI friend room ID", "optional")

    print("\nAnthropic")
    print("-" * 40)
    api_key = prompt("Anthropic API key", secret=True)

    print("\nVoting")
    print("-" * 40)
    vote_threshold = prompt("Net votes to canonize a proposal", default="3")
    friend_limit = prompt("Daily message limit to friend room", default="10")

    env_values = {
        "MATRIX_HOMESERVER": homeserver,
        "MATRIX_ACCESS_TOKEN": token,
        "MATRIX_BOT_USER": bot_user,
        "MATRIX_HUMAN_USER": human_user,
        "MATRIX_HUMAN_NAME": human_name,
        "MATRIX_ROOM_ID": room_id,
        "MATRIX_FRIEND_ROOM_ID": friend_room_id,
        "ANTHROPIC_API_KEY": api_key,
        "VOTE_THRESHOLD": vote_threshold,
        "FRIEND_MESSAGE_LIMIT": friend_limit,
    }

    print("\nMemory files")
    print("-" * 40)
    init_memory()

    print("\n.env")
    print("-" * 40)
    write_env(env_values)

    # --- Scheduler ---
    uv_path = shutil.which("uv") or "uv"
    system = platform.system()

    print("\nScheduler")
    print("-" * 40)

    if system == "Darwin":
        if yn("Set up launchd agents (macOS)?"):
            write_launchd_plists(uv_path)
    elif system == "Linux":
        if yn("Set up systemd user timers (Linux)?"):
            write_systemd_units(uv_path)
    else:
        print(f"  Unsupported platform: {system}. Set up scheduling manually.")
        print(f"  poll.py: run every 15 minutes")
        print(f"  daily.py: run once per day")

    print("\n=== Setup complete ===\n")
    print(f"  Project directory: {BASE_DIR}")
    print(f"  Run manually:      uv run poll.py / uv run daily.py")
    print()


if __name__ == "__main__":
    main()
