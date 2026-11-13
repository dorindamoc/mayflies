"""Minimal Ollama /api/chat client with native + text tool-call parsing."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field

import httpx

from config import Config


class LLMError(Exception):
    pass


@dataclass
class ToolCall:
    name: str
    arguments: dict


@dataclass
class LLMReply:
    content: str
    tool_calls: list = field(default_factory=list)
    prompt_tokens: int = 0
    eval_tokens: int = 0


_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)
_TOOL_BLOCK = re.compile(r"<tool_call>\s*(.*?)\s*</tool_call>", re.DOTALL)


def parse_text_tool_calls(content: str):
    """Fallback for models that emit <tool_call>{json}</tool_call> as plain text."""
    calls = []
    for raw in _TOOL_BLOCK.findall(content):
        try:
            obj = json.loads(raw)
            calls.append(ToolCall(obj["name"], obj.get("arguments") or {}))
        except (ValueError, KeyError, TypeError):
            continue
    return _TOOL_BLOCK.sub("", content).strip(), calls


def _args(raw) -> dict:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return {}
    return raw if isinstance(raw, dict) else {}


class LLMClient:
    RETRY_DELAYS = (5, 15, 45)

    def __init__(self, cfg: Config, transport=None, sleep=time.sleep):
        self.cfg = cfg
        self._sleep = sleep
        self._http = httpx.Client(base_url=cfg.ollama_host, timeout=900, transport=transport)

    def chat(self, messages, tools=None, model=None, think=None) -> LLMReply:
        payload = {
            "model": model or self.cfg.model_default,
            "messages": messages,
            "stream": False,
            "think": self.cfg.think if think is None else think,
            "options": {"num_ctx": self.cfg.num_ctx},
        }
        if tools:
            payload["tools"] = tools

        data = None
        for delay in tuple(self.RETRY_DELAYS) + (None,):
            try:
                resp = self._http.post("/api/chat", json=payload)
                resp.raise_for_status()
                data = resp.json()
                break
            except httpx.HTTPStatusError as e:
                if e.response.status_code < 500:
                    raise LLMError(f"ollama rejected request: {e}") from e
                if delay is None:
                    raise LLMError(f"ollama unavailable: {e}") from e
            except httpx.TransportError as e:
                if delay is None:
                    raise LLMError(f"ollama unreachable: {e}") from e
            self._sleep(delay)

        msg = data.get("message", {})
        content = _THINK.sub("", msg.get("content") or "").strip()
        calls = [ToolCall(c["function"]["name"], _args(c["function"].get("arguments")))
                 for c in (msg.get("tool_calls") or [])]
        if not calls:
            content, calls = parse_text_tool_calls(content)
        return LLMReply(content, calls, data.get("prompt_eval_count", 0), data.get("eval_count", 0))
