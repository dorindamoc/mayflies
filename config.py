"""Configuration for Mayflies gen 2, read from the environment / .env."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    home: Path
    ollama_host: str = "http://localhost:11434"
    model_default: str = "qwen3.8:27b"
    model_pool: tuple = ()
    model_weights: dict = field(default_factory=dict)
    model_think: dict = field(default_factory=dict)
    first_read_fraction: float = 0.33
    num_ctx: int = 32768
    num_predict: int = 8192
    response_reserve: int = 2048
    think: bool = False
    max_tool_rounds: int = 6
    max_population: int = 20
    education_picks: int = 3
    offer_expiry_rounds: int = 3
    initial_population: int = 10
    memory_fragment_max: int = 1000
    short_term_max: int = 500
    long_term_fraction: float = 0.5
    long_term_entry_max: int = 300
    vote_threshold: int = 3
    heartbeat_interval: int = 3600
    board_recent: int = 20
    temperature_min: float = 0.6
    temperature_max: float = 1.1
    presence_penalty: float = 0.5
    matrix_poll_seconds: int = 30
    matrix_homeserver: str = ""
    matrix_access_token: str = ""
    matrix_bot_user: str = ""
    matrix_human_user: str = ""
    matrix_human_name: str = "Dorin"
    matrix_room_id: str = ""
    website_path: str = ""
    website_publish: bool = False
    website_repo: str = ""
    website_token: str = ""
    website_base_branch: str = "main"

    def __post_init__(self):
        if not 0 < self.long_term_fraction <= 0.8:
            raise ValueError("LONG_TERM_FRACTION must be above 0 and at most 0.8")
        if not 1 <= self.max_population <= 20:
            raise ValueError("MAX_POPULATION must be between 1 and 20")
        if not 0 <= self.initial_population <= self.max_population:
            raise ValueError("INITIAL_POPULATION must not exceed MAX_POPULATION")
        if self.website_publish and not (self.website_repo and self.website_token):
            raise ValueError("WEBSITE_PUBLISH needs WEBSITE_REPO (owner/name) and WEBSITE_TOKEN")

    @property
    def models(self) -> tuple:
        """Models instances can be born on; defaults to just the default model."""
        return tuple(self.model_pool) or (self.model_default,)

    def think_for(self, model: str) -> bool:
        return self.model_think.get(model, self.think)

    @property
    def first_read_allowance(self) -> int:
        """Minimum tokens of heritage an instance reads in its first prompt."""
        return int(self.num_ctx * self.first_read_fraction)

    @property
    def memory_dir(self) -> Path:
        return self.home / "memory"

    @property
    def long_term_tokens(self) -> int:
        """The long-term memory an instance can hold; when it is full the instance has one last prompt."""
        return int(self.num_ctx * self.long_term_fraction)

    @property
    def memories_dir(self) -> Path:
        return self.memory_dir / "memories"

    @property
    def messages_dir(self) -> Path:
        return self.home / "messages"

    @property
    def website_dir(self) -> Path:
        return Path(self.website_path) if self.website_path else self.home / "website"

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

        def pairs(key: str, cast, default):
            out = {}
            for item in s(key, "").split(","):
                name, sep, val = item.strip().rpartition("=")
                if sep and name:
                    out[name.strip()] = cast(val.strip())
                elif item.strip():
                    out[item.strip()] = default
            return out

        pool = pairs("MODEL_POOL", int, 1)
        think_map = pairs("MODEL_THINK", lambda v: v.lower() in ("1", "true", "yes"), True)

        def i(key: str, default: int) -> int:
            return int(env.get(key, default))

        return cls(
            home=home,
            ollama_host=s("OLLAMA_HOST", cls.ollama_host),
            model_default=s("MODEL_DEFAULT", cls.model_default),
            model_pool=tuple(pool),
            model_weights=pool or {s("MODEL_DEFAULT", cls.model_default): 1},
            model_think=think_map,
            first_read_fraction=float(env.get("FIRST_READ_FRACTION", cls.first_read_fraction)),
            num_ctx=i("NUM_CTX", cls.num_ctx),
            num_predict=i("NUM_PREDICT", cls.num_predict),
            think=s("THINK", "false").lower() in ("1", "true", "yes"),
            max_tool_rounds=i("MAX_TOOL_ROUNDS", cls.max_tool_rounds),
            max_population=i("MAX_POPULATION", cls.max_population),
            education_picks=i("EDUCATION_PICKS", cls.education_picks),
            offer_expiry_rounds=i("OFFER_EXPIRY_ROUNDS", cls.offer_expiry_rounds),
            initial_population=i("INITIAL_POPULATION", cls.initial_population),
            memory_fragment_max=i("MEMORY_FRAGMENT_MAX", cls.memory_fragment_max),
            short_term_max=i("SHORT_TERM_MAX", cls.short_term_max),
            long_term_fraction=float(env.get("LONG_TERM_FRACTION", cls.long_term_fraction)),
            long_term_entry_max=i("LONG_TERM_ENTRY_MAX", cls.long_term_entry_max),
            vote_threshold=i("VOTE_THRESHOLD", cls.vote_threshold),
            heartbeat_interval=i("HEARTBEAT_INTERVAL", cls.heartbeat_interval),
            board_recent=i("BOARD_RECENT", cls.board_recent),
            temperature_min=float(env.get("TEMPERATURE_MIN", cls.temperature_min)),
            temperature_max=float(env.get("TEMPERATURE_MAX", cls.temperature_max)),
            presence_penalty=float(env.get("PRESENCE_PENALTY", cls.presence_penalty)),
            matrix_poll_seconds=i("MATRIX_POLL_SECONDS", cls.matrix_poll_seconds),
            matrix_homeserver=s("MATRIX_HOMESERVER", "").rstrip("/"),
            matrix_access_token=s("MATRIX_ACCESS_TOKEN", ""),
            matrix_bot_user=s("MATRIX_BOT_USER", ""),
            matrix_human_user=s("MATRIX_HUMAN_USER", ""),
            matrix_human_name=s("MATRIX_HUMAN_NAME", "Dorin"),
            matrix_room_id=s("MATRIX_ROOM_ID", ""),
            website_path=s("WEBSITE_DIR", ""),
            website_publish=s("WEBSITE_PUBLISH", "false").lower() in ("1", "true", "yes"),
            website_repo=s("WEBSITE_REPO", ""),
            website_token=s("WEBSITE_TOKEN", ""),
            website_base_branch=s("WEBSITE_BASE_BRANCH", cls.website_base_branch),
        )
