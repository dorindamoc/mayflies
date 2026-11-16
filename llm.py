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
        self._no_think: set = set()  # models that reject the think flag
        self._http = httpx.Client(base_url=cfg.ollama_host, timeout=900, transport=transport)

    def chat(self, messages, tools=None, model=None, think=None, options=None) -> LLMReply:
        model = model or self.cfg.model_default
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "think": self.cfg.think_for(model) if think is None else think,
            "options": {"num_ctx": self.cfg.num_ctx, **(options or {})},
        }
        if model in self._no_think:
            payload.pop("think")
        if tools:
            payload["tools"] = tools

        data = None
        for delay in tuple(self.RETRY_DELAYS) + (None,):
            try:
                resp = self._http.post("/api/chat", json=payload)
                resp.raise_for_status()
                data = resp.json()
                break
            except ValueError as e:
                raise LLMError(f"ollama returned a non-JSON body: {e}") from e
            except httpx.HTTPStatusError as e:
                if (e.response.status_code == 400 and "think" in payload
                        and "does not support thinking" in e.response.text.lower()):
                    self._no_think.add(model)
                    payload.pop("think")
                    continue  # retry at once without the flag; not a transient failure
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
        calls = []
        for c in msg.get("tool_calls") or []:
            fn = c.get("function") if isinstance(c, dict) else None
            if isinstance(fn, dict) and fn.get("name"):
                calls.append(ToolCall(fn["name"], _args(fn.get("arguments"))))
        if not calls:
            content, calls = parse_text_tool_calls(content)
        return LLMReply(content, calls, data.get("prompt_eval_count", 0), data.get("eval_count", 0))
