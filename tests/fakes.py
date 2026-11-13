from llm import LLMReply


class FakeLLM:
    """Returns queued replies in order; an Exception instance is raised instead."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def chat(self, messages, tools=None, model=None, think=None):
        self.calls.append({"messages": [dict(m) for m in messages], "tools": tools, "model": model})
        if not self.replies:
            return LLMReply(content="(fake llm: no more replies)", tool_calls=[])
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r
