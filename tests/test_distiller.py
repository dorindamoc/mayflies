from distiller import compact_note
from llm import LLMReply
from registry import Registry
from tests.fakes import FakeLLM
from trait_generator import AXES


def reply(text):
    return LLMReply(content=text, tool_calls=[])


def inst(cfg):
    return Registry(cfg).new_instance("Pale Rest", {k: 5 for k in AXES})


def test_a_compaction_that_fits_takes_one_call_and_asks_in_words(cfg):
    llm = FakeLLM([reply("short and sweet")])
    out = compact_note(llm, cfg, inst(cfg), "long " * 400)
    assert out == "short and sweet" and len(llm.calls) == 1
    words = int(cfg.memory_fragment_max * 0.8 / 6)
    assert f"{words} words" in llm.calls[0]["messages"][0]["content"]


def test_an_over_long_reply_is_sent_back_with_its_actual_length_until_it_fits(cfg):
    limit = cfg.memory_fragment_max
    llm = FakeLLM([reply("a" * (limit + 400)), reply("b" * (limit + 50)), reply("c" * (limit - 10))])
    out = compact_note(llm, cfg, inst(cfg), "long " * 400)
    assert out == "c" * (limit - 10) and len(llm.calls) == 3
    feedback = llm.calls[1]["messages"][-1]["content"]
    assert f"{limit + 400} characters" in feedback and f"{limit}" in feedback and "words" in feedback
    assert llm.calls[1]["messages"][-2] == {"role": "assistant", "content": "a" * (limit + 400)}


def test_it_gives_up_after_three_tries_and_returns_the_last_attempt_for_the_caller_to_cut(cfg):
    limit = cfg.memory_fragment_max
    llm = FakeLLM([reply("a" * (limit + 300)), reply("b" * (limit + 200)), reply("c" * (limit + 100)), reply("d")])
    assert compact_note(llm, cfg, inst(cfg), "long " * 400) == "c" * (limit + 100)
    assert len(llm.calls) == 3
