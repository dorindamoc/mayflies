from distiller import compact_note, distill, fold
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


def test_distill_recaps_one_prompt_within_the_short_term_limit(cfg):
    llm = FakeLLM([reply("word " * 400)])
    out = distill(llm, cfg, inst(cfg), "heartbeat", "final words", ["read_website: {}"])
    assert len(out) <= cfg.short_term_max and not out.endswith("wor")
    user = llm.calls[0]["messages"][1]["content"]
    assert "read_website" in user and "final words" in user and "Previous recollection" not in user


def test_distill_asks_for_what_was_made_read_and_learned(cfg):
    llm = FakeLLM([reply("r")])
    distill(llm, cfg, inst(cfg), "heartbeat", "x", ["a"])
    system = llm.calls[0]["messages"][0]["content"].lower()
    assert "made" in system and "read" in system and "took from" in system


def test_fold_compacts_short_term_into_a_long_term_entry(cfg):
    llm = FakeLLM([reply("compact entry")])
    assert fold(llm, cfg, inst(cfg), "I read.\n\nI wanted to remember: x") == "compact entry"
    assert "words" in llm.calls[0]["messages"][0]["content"]
    assert "I wanted to remember: x" in llm.calls[0]["messages"][1]["content"]


def test_fold_cuts_an_over_long_entry_and_survives_a_model_failure(cfg):
    out = fold(FakeLLM([reply("word " * 400)]), cfg, inst(cfg), "short term text")
    assert len(out) <= cfg.long_term_entry_max
    from llm import LLMError
    assert fold(FakeLLM([LLMError("down")]), cfg, inst(cfg), "short term text") == "short term text"
    assert len(fold(FakeLLM([LLMError("down")]), cfg, inst(cfg), "w " * 400)) <= cfg.long_term_entry_max


def test_fold_asks_in_words_and_asks_again_when_the_entry_is_too_long(cfg):
    long = "I built a thing and it was good. " * 20
    llm = FakeLLM([reply(long), reply("I built a thing.")])
    assert fold(llm, cfg, inst(cfg), "short term text") == "I built a thing."
    assert "words" in llm.calls[0]["messages"][0]["content"]
    assert str(len(long.strip())) in llm.calls[1]["messages"][-1]["content"]


def test_fold_last_resort_cut_ends_at_a_sentence(cfg):
    sentence = "I built the lattice and left it open for the others. "
    out = fold(FakeLLM([reply(sentence * 20)] * 3), cfg, inst(cfg), "short term text")
    assert len(out) <= cfg.long_term_entry_max and out.endswith(".")
