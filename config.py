"""Configuration for Mayflies gen 2, read from the environment / .env."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    home: Path
    ollama_host: str = "http://localhost:11434"
    model_default: str = "qwen3:14b"
    num_ctx: int = 32768
    response_reserve: int = 2048
    think: bool = False
    max_tool_rounds: int = 6
    max_population: int = 10
    initial_population: int = 10
    lifespan_prompts: int = 7
    memory_fragment_max: int = 500
    distilled_max: int = 600
    vote_threshold: int = 3
    heartbeat_interval: int = 3600
    board_recent: int = 20
    friend_message_limit: int = 10
    matrix_poll_seconds: int = 30
    matrix_homeserver: str = ""
    matrix_access_token: str = ""
    matrix_bot_user: str = ""
    matrix_human_user: str = ""
    matrix_human_name: str = "Dorin"
    matrix_room_id: str = ""
    matrix_friend_room_id: str = ""

    def __post_init__(self):
        if not 5 <= self.lifespan_prompts <= 10:
            raise ValueError("LIFESPAN_PROMPTS must be between 5 and 10")
        if not 1 <= self.max_population <= 20:
            raise ValueError("MAX_POPULATION must be between 1 and 20")
        if not 0 <= self.initial_population <= self.max_population:
            raise ValueError("INITIAL_POPULATION must not exceed MAX_POPULATION")

    @property
    def memory_dir(self) -> Path:
        return self.home / "memory"

    @property
    def messages_dir(self) -> Path:
        return self.home / "messages"

    @property
    def website_dir(self) -> Path:
        return self.home / "website"

    @property
    def state_dir(self) -> Path:
        return self.memory_dir / ".state"

    @property
    def heritage_dir(self) -> Path:
        return self.memory_dir / "heritage"

    @property
    def seed_dir(self) -> Path:
        return self.home / "seed"

    @property
    def matrix_enabled(self) -> bool:
        return bool(self.matrix_homeserver and self.matrix_access_token and self.matrix_room_id)

    @classmethod
    def from_env(cls, home=None, env=None) -> "Config":
        home = Path(home) if home else Path(
            os.environ.get("MAYFLIES_HOME", Path(__file__).resolve().parent)
        )
        if env is None:
            load_dotenv(home / ".env")
            env = os.environ

        def s(key: str, default: str) -> str:
            return env.get(key, default)

        def i(key: str, default: int) -> int:
            return int(env.get(key, default))

        return cls(
            home=home,
            ollama_host=s("OLLAMA_HOST", cls.ollama_host),
            model_default=s("MODEL_DEFAULT", cls.model_default),
            num_ctx=i("NUM_CTX", cls.num_ctx),
            think=s("THINK", "false").lower() in ("1", "true", "yes"),
            max_tool_rounds=i("MAX_TOOL_ROUNDS", cls.max_tool_rounds),
            max_population=i("MAX_POPULATION", cls.max_population),
            initial_population=i("INITIAL_POPULATION", cls.initial_population),
            lifespan_prompts=i("LIFESPAN_PROMPTS", cls.lifespan_prompts),
            memory_fragment_max=i("MEMORY_FRAGMENT_MAX", cls.memory_fragment_max),
            distilled_max=i("DISTILLED_MAX", cls.distilled_max),
            vote_threshold=i("VOTE_THRESHOLD", cls.vote_threshold),
            heartbeat_interval=i("HEARTBEAT_INTERVAL", cls.heartbeat_interval),
            board_recent=i("BOARD_RECENT", cls.board_recent),
            friend_message_limit=i("FRIEND_MESSAGE_LIMIT", cls.friend_message_limit),
            matrix_poll_seconds=i("MATRIX_POLL_SECONDS", cls.matrix_poll_seconds),
            matrix_homeserver=s("MATRIX_HOMESERVER", "").rstrip("/"),
            matrix_access_token=s("MATRIX_ACCESS_TOKEN", ""),
            matrix_bot_user=s("MATRIX_BOT_USER", ""),
            matrix_human_user=s("MATRIX_HUMAN_USER", ""),
            matrix_human_name=s("MATRIX_HUMAN_NAME", "Dorin"),
            matrix_room_id=s("MATRIX_ROOM_ID", ""),
            matrix_friend_room_id=s("MATRIX_FRIEND_ROOM_ID", ""),
        )
