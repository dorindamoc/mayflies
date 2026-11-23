"""Shared objects passed to the scheduler, heartbeat, and prompt builder."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from config import Config
from heritage import Catalog
from llm import LLMClient
from matrix import MatrixClient
from registry import Registry
from store import Store


@dataclass
class Runtime:
    cfg: Config
    llm: object
    store: Store
    catalog: Catalog
    registry: Registry
    matrix: Optional[MatrixClient]

    @classmethod
    def build(cls, cfg: Config) -> "Runtime":
        return cls(cfg=cfg, llm=LLMClient(cfg), store=Store(cfg), catalog=Catalog(cfg.heritage_dir),
                   registry=Registry(cfg), matrix=MatrixClient(cfg) if cfg.matrix_enabled else None)
