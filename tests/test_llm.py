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
    assert seen["model"] == "qwen3.8:27b" and seen["think"] is False
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


def test_non_json_success_body_is_llm_error(cfg):
    with pytest.raises(LLMError):
        client(cfg, lambda req: httpx.Response(200, text="<html>proxy</html>")).chat([])


def test_malformed_native_tool_call_is_skipped(cfg):
    def handler(req):
        return httpx.Response(200, json={"message": {"content": "x", "tool_calls": [
            {"function": {}}, {"nofunction": 1}, {"function": {"name": "die", "arguments": {}}}]}})

    assert client(cfg, handler).chat([]).tool_calls == [ToolCall("die", {})]


def test_per_call_options_merge_with_num_ctx(cfg):
    seen = {}

    def handler(req):
        seen.update(json.loads(req.content))
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "hi"}})

    client(cfg, handler).chat([{"role": "user", "content": "x"}], options={"temperature": 0.9})
    assert seen["options"] == {"num_ctx": 32768, "temperature": 0.9}


def test_think_flag_follows_the_models_setting(tmp_path):
    from config import Config
    cfg2 = Config.from_env(home=tmp_path, env={"THINK": "false", "MODEL_THINK": "qwen3:27b=true"})
    seen = []

    def handler(req):
        seen.append(json.loads(req.content))
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "ok"}})

    c = client(cfg2, handler)
    c.chat([], model="qwen3:27b")
    c.chat([], model="llama3:70b")
    c.chat([], model="qwen3:27b", think=False)
    assert [b["think"] for b in seen] == [True, False, False]


def test_model_without_thinking_support_is_retried_without_think_and_remembered(cfg):
    bodies = []

    def handler(req):
        body = json.loads(req.content)
        bodies.append(body)
        if "think" in body and body["model"] == "llama3:70b":
            return httpx.Response(400, json={"error": "\"llama3:70b\" does not support thinking"})
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "ok"}})

    c = client(cfg, handler)
    assert c.chat([{"role": "user", "content": "x"}], model="llama3:70b").content == "ok"
    assert c.chat([{"role": "user", "content": "y"}], model="llama3:70b").content == "ok"
    assert ["think" in b for b in bodies] == [True, False, False]
    c.chat([{"role": "user", "content": "z"}], model="qwen3:14b")
    assert "think" in bodies[-1]


def test_bare_json_in_plain_text_is_not_treated_as_a_tool_call(cfg):
    text = 'Here is an example: {"name": "read_heritage", "parameters": {"id": "H-001"}}'

    def handler(req):
        return httpx.Response(200, json={"message": {"role": "assistant", "content": text}})

    spec = {"type": "function", "function": {"name": "read_heritage", "description": "d",
                                              "parameters": {"type": "object", "properties": {}}}}
    reply = client(cfg, handler).chat([], tools=[spec])
    assert reply.tool_calls == [] and reply.content == text
