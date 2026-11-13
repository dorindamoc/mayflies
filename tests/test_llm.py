import json
import httpx
import pytest
from llm import LLMClient, LLMError, ToolCall, parse_text_tool_calls


def client(cfg, handler, sleeps=None):
    return LLMClient(cfg, transport=httpx.MockTransport(handler),
                     sleep=(sleeps.append if sleeps is not None else (lambda s: None)))


def test_plain_reply_and_payload(cfg):
    seen = {}

    def handler(req):
        seen.update(json.loads(req.content))
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "hi"},
                                         "prompt_eval_count": 10, "eval_count": 3})

    r = client(cfg, handler).chat([{"role": "user", "content": "x"}])
    assert r.content == "hi" and r.prompt_tokens == 10 and r.tool_calls == []
    assert seen["model"] == "qwen3:14b" and seen["think"] is False
    assert seen["options"]["num_ctx"] == 32768 and seen["stream"] is False


def test_native_tool_calls_and_string_arguments(cfg):
    def handler(req):
        return httpx.Response(200, json={"message": {"content": "", "tool_calls": [
            {"function": {"name": "board_post", "arguments": {"text": "a"}}},
            {"function": {"name": "vote", "arguments": "{\"proposal_id\": \"P-1\"}"}},
        ]}})

    r = client(cfg, handler).chat([], tools=[{"x": 1}])
    assert r.tool_calls == [ToolCall("board_post", {"text": "a"}), ToolCall("vote", {"proposal_id": "P-1"})]


def test_think_blocks_stripped(cfg):
    def handler(req):
        return httpx.Response(200, json={"message": {"content": "<think>hmm</think>answer"}})

    assert client(cfg, handler).chat([]).content == "answer"


def test_text_tool_call_fallback():
    content = 'Sure.\n<tool_call>\n{"name": "die", "arguments": {"reason": "done"}}\n</tool_call>'
    clean, calls = parse_text_tool_calls(content)
    assert calls == [ToolCall("die", {"reason": "done"})] and clean == "Sure."


def test_text_tool_call_malformed_json_is_ignored():
    clean, calls = parse_text_tool_calls("<tool_call>{not json}</tool_call> ok")
    assert calls == [] and "ok" in clean


def test_retries_on_5xx_then_succeeds(cfg):
    attempts = []

    def handler(req):
        attempts.append(1)
        if len(attempts) < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"message": {"content": "ok"}})

    sleeps = []
    assert client(cfg, handler, sleeps).chat([]).content == "ok"
    assert len(attempts) == 3 and sleeps == [5, 15]


def test_gives_up_with_llm_error(cfg):
    with pytest.raises(LLMError):
        client(cfg, lambda req: httpx.Response(503)).chat([])


def test_4xx_is_immediate_error(cfg):
    attempts = []

    def handler(req):
        attempts.append(1)
        return httpx.Response(404, json={"error": "model not found"})

    with pytest.raises(LLMError):
        client(cfg, handler).chat([])
    assert len(attempts) == 1
