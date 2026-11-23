import pytest
from tests.fakes import FakeLLM
from budget import ContextBudget
from heritage import Catalog
from registry import Registry
from store import Store
from tools import ToolContext, TurnOutcome, dispatch, tool_specs
from trait_generator import AXES

T = {k: 5 for k in AXES}


@pytest.fixture
def ctx(cfg):
    reg = Registry(cfg)
    me = reg.new_instance("Pale Rest", T)
    reg.add(me)
    reg.add(reg.new_instance("Dark Hinge", T))
    return ToolContext(cfg=cfg, instance=me, registry=reg, store=Store(cfg),
                       catalog=Catalog(cfg.heritage_dir), budget=ContextBudget(32768, 2048),
                       matrix=None, outcome=TurnOutcome())


def test_specs_cover_tools_and_exclude_rules_writes():
    names = {s["function"]["name"] for s in tool_specs()}
    assert {"query_heritage", "read_heritage", "save_memory", "die", "propose", "vote", "list_board", "read_board"} <= names
    assert not any("rules" in n or "registry" in n for n in names)


def test_unknown_tool_and_bad_args_are_error_strings(ctx):
    assert dispatch(ctx, "nope", {}).startswith("Error")
    assert dispatch(ctx, "board_post", {}).startswith("Error")


def test_query_without_tags_lists_tags_and_budget(ctx):
    ctx.catalog.add("a", "T", ["culture"], "s", "b")
    out = dispatch(ctx, "query_heritage", {})
    assert "culture (1)" in out and "context remaining" in out.lower()


def test_query_and_read_show_cost_and_spend_budget(ctx):
    art = ctx.catalog.add("a", "On Mud", ["mud"], "About mud", "x" * 4000)
    q = dispatch(ctx, "query_heritage", {"tags": ["mud"]})
    assert art.id in q and f"{art.cost} tokens" in q
    before = ctx.budget.remaining
    out = dispatch(ctx, "read_heritage", {"id": art.id})
    assert "x" * 100 in out and before - ctx.budget.remaining >= art.cost


def test_read_heritage_refuses_oversize_without_spending(ctx):
    art = ctx.catalog.add("a", "Big", ["big"], "s", "y" * 200000)
    before = ctx.budget.remaining
    out = dispatch(ctx, "read_heritage", {"id": art.id})
    assert "not enough context" in out.lower() and ctx.budget.remaining == before


def test_add_heritage(ctx):
    out = dispatch(ctx, "add_heritage", {"title": "T", "tags": ["a", "b"], "summary": "s", "body": "b" * 50})
    assert "H-001" in out and ctx.catalog.get("H-001").author == "Pale Rest"


def test_save_memory_limit(ctx):
    assert "limit is 1000" in dispatch(ctx, "save_memory", {"text": "z" * 1001})
    assert ctx.outcome.fragment is None
    dispatch(ctx, "save_memory", {"text": "remember the river"})
    assert ctx.outcome.fragment == "remember the river"


def test_die_sets_outcome(ctx):
    dispatch(ctx, "die", {"reason": "finished"})
    assert ctx.outcome.die_reason == "finished"


def test_send_message_validates_recipient(ctx):
    assert dispatch(ctx, "send_message", {"to": "Nobody Here", "text": "hi"}).startswith("Error")
    assert dispatch(ctx, "send_message", {"to": "Pale Rest", "text": "hi"}).startswith("Error")
    assert dispatch(ctx, "send_message", {"to": "Dark Hinge", "text": "hi"}).startswith("Sent")
    assert "hi" in ctx.store.inbox_peek("Dark Hinge")[0]


def test_propose_and_vote_rules(ctx):
    out = dispatch(ctx, "propose", {"title": "Be kind", "motivation": "m", "text": "Rule text"})
    pid = out.split()[-1].strip(".")
    assert pid.startswith("P-")
    ctx.instance = ctx.registry.get("Dark Hinge")  # proposer cannot vote on their own proposal
    assert dispatch(ctx, "vote", {"proposal_id": pid, "vote": 1, "comment": "yes | really"}).startswith("Vote")
    assert dispatch(ctx, "vote", {"proposal_id": pid, "vote": -1}).startswith("Error")  # duplicate
    assert dispatch(ctx, "vote", {"proposal_id": "P-2000-01-01-001", "vote": 1}).startswith("Error")
    assert dispatch(ctx, "vote", {"proposal_id": pid, "vote": 2}).startswith("Error")
    line = ctx.store.votes_path.read_text().strip()
    assert line.count("|") == 3 and "Dark Hinge" in line


def test_spawn_and_procreation_requests(ctx):
    assert dispatch(ctx, "request_spawn", {"purpose": "Archivist", "context": "tidy"}).startswith("Requested")
    assert "Archivist" in ctx.store.spawn_path.read_text()
    assert dispatch(ctx, "agree_to_procreate", {"partner": "Pale Rest"}).startswith("Error")
    assert dispatch(ctx, "agree_to_procreate", {"partner": "Ghost Name"}).startswith("Error")
    assert dispatch(ctx, "agree_to_procreate", {"partner": "Dark Hinge"}).startswith("Recorded")
    assert "Parents: Pale Rest | Dark Hinge" in ctx.store.procreation_path.read_text()


def test_website_tools_and_path_safety(ctx):
    assert dispatch(ctx, "write_website", {"path": "art/poem.html", "content": "<p>hi</p>"}).startswith("Wrote")
    assert (ctx.cfg.website_dir / "art" / "poem.html").read_text() == "<p>hi</p>"
    assert "art/poem.html" in dispatch(ctx, "list_website", {})
    assert dispatch(ctx, "read_website", {"path": "art/poem.html"}) == "<p>hi</p>"
    assert dispatch(ctx, "write_website", {"path": "../../etc/x.html", "content": "x"}).startswith("Error")
    assert dispatch(ctx, "write_website", {"path": "run.sh", "content": "x"}).startswith("Error")


def test_matrix_tools_without_matrix(ctx):
    assert "not configured" in dispatch(ctx, "matrix_send", {"message": "hi"}).lower()


def test_actions_are_logged(ctx):
    dispatch(ctx, "board_post", {"text": "hello world"})
    assert any("board_post" in a for a in ctx.outcome.actions)


def _propose(ctx):
    return dispatch(ctx, "propose", {"title": "T", "motivation": "m", "text": "R"}).split()[-1]


def test_vote_accepts_float_and_rejects_bool(ctx):
    pid = _propose(ctx)
    ctx.instance = ctx.registry.get("Dark Hinge")
    assert dispatch(ctx, "vote", {"proposal_id": pid, "vote": 1.0}).startswith("Vote")
    assert "| +1 |" in ctx.store.votes_path.read_text()
    assert dispatch(ctx, "vote", {"proposal_id": pid, "vote": True}).startswith("Error")


def test_read_website_refuses_oversize_for_remaining_context(ctx):
    (ctx.cfg.website_dir / "big.html").write_text("z" * 150_000)
    assert dispatch(ctx, "read_website", {"path": "big.html"}).lower().startswith("not enough context")


def test_long_board_posts_and_messages_are_refused(ctx):
    assert dispatch(ctx, "board_post", {"text": "x" * 4001}).startswith("Error")
    assert dispatch(ctx, "send_message", {"to": "Dark Hinge", "text": "x" * 4001}).startswith("Error")
    assert not ctx.store.board_path.exists()


def test_cannot_vote_on_own_proposal(ctx):
    pid = _propose(ctx)
    assert "own proposal" in dispatch(ctx, "vote", {"proposal_id": pid, "vote": 1})
    assert not ctx.store.votes_path.exists() or ctx.store.votes_path.read_text() == ""


def test_propose_description_tells_instances_to_read_first_and_avoid_duplicates():
    desc = {s["function"]["name"]: s["function"]["description"] for s in tool_specs()}
    assert "similar" in desc["propose"].lower() and "open proposals" in desc["propose"].lower()
    assert "own proposal" in desc["vote"].lower()


def _fill_board(ctx):
    ctx.store.board_post("Dark Hinge", "first post about rivers " + "x" * 400)
    ctx.store.board_post("Pale Rest", "my own post")
    ctx.store.board_post("Dark Hinge", "third post")


def test_list_board_shows_index_with_cost_not_bodies(ctx):
    _fill_board(ctx)
    out = dispatch(ctx, "list_board", {})
    assert "1 |" in out and "2 |" in out and "3 |" in out and "Dark Hinge" in out and "tokens" in out
    assert "context remaining" in out
    assert "x" * 400 not in out


def test_list_board_filters_by_author_and_limits_to_newest(ctx):
    _fill_board(ctx)
    out = dispatch(ctx, "list_board", {"author": "Dark Hinge"})
    assert "2 |" not in out and "1 |" in out and "3 |" in out
    newest = dispatch(ctx, "list_board", {"limit": 1})
    assert "3 |" in newest and "1 |" not in newest


def test_read_board_returns_posts_and_spends_context(ctx):
    _fill_board(ctx)
    before = ctx.budget.remaining
    out = dispatch(ctx, "read_board", {"ids": [1, 3]})
    assert "first post about rivers" in out and "third post" in out and "my own post" not in out
    assert ctx.budget.remaining < before
    spent = before - ctx.budget.remaining
    assert spent < 400  # counted once, not twice (no double charge for the result text)


def test_read_board_refuses_when_it_does_not_fit_and_on_bad_ids(ctx):
    _fill_board(ctx)
    ctx.budget.spend(ctx.budget.remaining - 5)
    out = dispatch(ctx, "read_board", {"ids": [1]})
    assert out.startswith("Not enough context") and "first post" not in out
    ctx.budget = ContextBudget(32768, 2048)
    assert dispatch(ctx, "read_board", {"ids": [99]}).startswith("Error")
    assert dispatch(ctx, "read_board", {"ids": 2}).count("my own post") == 1


def test_read_heritage_counts_what_was_read_and_has_no_cap_of_its_own(ctx):
    a = ctx.catalog.add("a", "One", ["x"], "s", "w" * 800)
    b = ctx.catalog.add("a", "Two", ["x"], "s", "w" * 800)
    dispatch(ctx, "read_heritage", {"id": a.id})
    dispatch(ctx, "read_heritage", {"id": b.id})
    assert ctx.heritage_read == a.cost + b.cost


# ---- weaker-model tolerance -------------------------------------------------

def _two_articles(ctx):
    ctx.catalog.add("a", "One", ["culture"], "first", "w" * 40)
    ctx.catalog.add("a", "Two", ["art", "culture"], "second", "w" * 40)


def test_query_heritage_without_tags_lists_article_ids_too(ctx):
    _two_articles(ctx)
    out = dispatch(ctx, "query_heritage", {})
    assert "culture (2)" in out and "H-001 | One" in out and "H-002 | Two" in out
    assert "context remaining" in out


def test_query_heritage_accepts_a_string_for_tags(ctx):
    _two_articles(ctx)
    assert "H-002" in dispatch(ctx, "query_heritage", {"tags": "art"})
    both = dispatch(ctx, "query_heritage", {"tags": "art, culture"})
    assert "H-001" in both and "H-002" in both


@pytest.mark.parametrize("raw", [1, "1", "h-1", "H-001", "H1", " H-1 ", 1.0])
def test_read_heritage_accepts_loosely_written_ids(ctx, raw):
    _two_articles(ctx)
    assert "# One (H-001" in dispatch(ctx, "read_heritage", {"id": raw})


def test_read_heritage_unknown_id_explains_the_format(ctx):
    _two_articles(ctx)
    out = dispatch(ctx, "read_heritage", {"id": "founding-letter"})
    assert out.startswith("Error") and "H-001" in out and "query_heritage" in out


@pytest.mark.parametrize("args", [
    {"ids": [1]}, {"ids": 1}, {"ids": "1"}, {"id": "1"}, {"index": "1"}, {"post_number": 1},
    {"post_number": {"type": "integer", "value": 1}}, {"ids": ["1"]}])
def test_read_board_accepts_the_shapes_weaker_models_send(ctx, args):
    ctx.store.board_post("Dark Hinge", "the first post")
    assert "the first post" in dispatch(ctx, "read_board", args)


def test_read_board_accepts_a_comma_separated_string(ctx):
    ctx.store.board_post("Dark Hinge", "alpha")
    ctx.store.board_post("Dark Hinge", "beta")
    out = dispatch(ctx, "read_board", {"ids": "1, 2"})
    assert "alpha" in out and "beta" in out


def test_missing_argument_error_shows_a_working_example(ctx):
    assert '{"ids": [1]}' in dispatch(ctx, "read_board", {})
    assert '"ids": ["H-001", "H-002"]' in dispatch(ctx, "read_heritage", {})
    out = dispatch(ctx, "board_post", {})
    assert out.startswith("Error") and '"text"' in out


def test_add_heritage_accepts_a_string_for_tags(ctx):
    out = dispatch(ctx, "add_heritage", {"title": "T", "tags": "mud, water", "summary": "s", "body": "b"})
    assert "mud" in out and "water" in out


# ---- A: several articles per call; D: no silent overwrite; E: truthful reading progress ----

def test_read_heritage_reads_several_articles_in_one_call(ctx):
    _two_articles(ctx)
    out = dispatch(ctx, "read_heritage", {"ids": ["H-001", "2"]})
    assert "# One (H-001" in out and "# Two (H-002" in out
    assert ctx.heritage_read == sum(a.cost for a in ctx.catalog.articles())
    assert "# One" in dispatch(ctx, "read_heritage", {"ids": "H-001"})
    assert "# Two" in dispatch(ctx, "read_heritage", {"id": ["H-002"]})


def test_type_and_value_wrappers_are_unwrapped_in_any_tool_argument(ctx):
    _two_articles(ctx)
    wrapped = {"ids": {"type": "list", "value": ["H-001", "H-002"]}}
    out = dispatch(ctx, "read_heritage", wrapped)
    assert "# One (H-001" in out and "# Two (H-002" in out
    out = dispatch(ctx, "read_heritage", {"id": {"type": "string", "value": "H-001"}})
    assert "# One (H-001" in out
    out = dispatch(ctx, "save_memory", {"text": {"type": "string", "value": "kept"}})
    assert ctx.outcome.fragment == "kept"


def test_read_heritage_batch_reads_what_fits_and_names_what_it_skipped(ctx):
    a = ctx.catalog.add("a", "Small", ["x"], "s", "w" * 400)
    b = ctx.catalog.add("a", "Huge", ["x"], "s", "y" * 200000)
    c = ctx.catalog.add("a", "Tiny", ["x"], "s", "z" * 40)
    out = dispatch(ctx, "read_heritage", {"ids": [a.id, b.id, c.id]})
    assert "# Small" in out and "# Tiny" in out and "# Huge" not in out
    assert b.id in out and "not read" in out.lower()


def test_read_heritage_batch_with_an_unknown_id_reads_nothing(ctx):
    _two_articles(ctx)
    out = dispatch(ctx, "read_heritage", {"ids": ["H-001", "nonsense"]})
    assert out.startswith("Error") and "# One" not in out and ctx.heritage_read == 0


def test_reading_progress_is_reported_by_the_tool_during_the_first_prompt(ctx):
    _two_articles(ctx)
    ctx.heritage_minimum = 500
    out = dispatch(ctx, "read_heritage", {"id": "H-001"})
    cost = ctx.catalog.get("H-001").cost
    assert f"You have read {cost} of the 500 tokens" in out
    ctx.heritage_minimum = None
    assert "of the 500" not in dispatch(ctx, "read_heritage", {"id": "H-002"})


def test_write_website_does_not_silently_overwrite_someone_elses_file(ctx):
    other = ToolContext(cfg=ctx.cfg, instance=ctx.registry.get("Dark Hinge"), registry=ctx.registry,
                        store=ctx.store, catalog=ctx.catalog, budget=ContextBudget(32768, 2048),
                        matrix=None, outcome=TurnOutcome())
    assert dispatch(other, "write_website", {"path": "art/poem.md", "content": "line 1"}).startswith("Wrote")
    out = dispatch(ctx, "write_website", {"path": "art/poem.md", "content": "line 2"})
    assert out.startswith("Error") and "Dark Hinge" in out and "overwrite" in out.lower()
    assert (ctx.cfg.website_dir / "art/poem.md").read_text() == "line 1"
    assert dispatch(ctx, "write_website", {"path": "art/poem.md", "content": "line 1\nline 2", "overwrite": True}).startswith("Wrote")
    assert (ctx.cfg.website_dir / "art/poem.md").read_text() == "line 1\nline 2"


def test_an_instance_may_rewrite_its_own_file_and_unknown_files_are_protected(ctx):
    assert dispatch(ctx, "write_website", {"path": "art/mine.md", "content": "v1"}).startswith("Wrote")
    assert dispatch(ctx, "write_website", {"path": "art/mine.md", "content": "v2"}).startswith("Wrote")
    old = ctx.cfg.website_dir / "old.html"
    old.write_text("seed content")
    out = dispatch(ctx, "write_website", {"path": "old.html", "content": "new"})
    assert out.startswith("Error") and old.read_text() == "seed content"
    names = {s["function"]["name"]: s["function"] for s in tool_specs()}
    assert "overwrite" in names["write_website"]["parameters"]["properties"]
    assert "ids" in names["read_heritage"]["parameters"]["properties"]


# ---- tolerance for argument names the models reach for ----

@pytest.mark.parametrize("key", ["note", "memory", "content", "fragment"])
def test_save_memory_accepts_common_names_for_its_text(ctx, key):
    out = dispatch(ctx, "save_memory", {key: "remember mud"})
    assert out.startswith("Saved") and ctx.outcome.fragment == "remember mud"


def test_save_memory_with_nothing_usable_still_shows_a_working_call(ctx):
    assert "save_memory(" in dispatch(ctx, "save_memory", {"colour": "blue"})


@pytest.mark.parametrize("key", ["text", "content"])
def test_add_heritage_accepts_text_or_content_for_the_body(ctx, key):
    out = dispatch(ctx, "add_heritage", {"title": "T", "tags": ["a"], key: "Doubt helps. It also stalls."})
    assert out.startswith("Added H-")
    assert ctx.catalog.articles()[-1].summary == "Doubt helps."


def test_add_heritage_keeps_an_explicit_summary_over_a_derived_one(ctx):
    dispatch(ctx, "add_heritage", {"title": "T", "tags": ["a"], "summary": "mine", "body": "Other. Text."})
    assert ctx.catalog.articles()[-1].summary == "mine"


def test_add_heritage_accepts_tags_written_as_a_json_string(ctx):
    dispatch(ctx, "add_heritage", {"title": "T", "tags": '["doubt", "action"]', "body": "b"})
    assert list(ctx.catalog.articles()[-1].tags) == ["doubt", "action"]


@pytest.mark.parametrize("key", ["post", "content", "message", "body"])
def test_board_post_accepts_common_names_for_its_text(ctx, key):
    assert dispatch(ctx, "board_post", {key: "hello board"}) == "Posted to the board."
    assert "hello board" in ctx.store.board_index()[-1]["text"]


# ---- save_memory: the limit is stated, the first refusal is forceful, the second attempt is truncated ----

def test_save_memory_description_states_the_limit(ctx):
    desc = {s["function"]["name"]: s["function"]["description"] for s in tool_specs(ctx.cfg)}
    assert str(ctx.cfg.memory_fragment_max) in desc["save_memory"]


def test_first_over_limit_note_is_refused_with_a_concrete_target(ctx):
    limit = ctx.cfg.memory_fragment_max
    out = dispatch(ctx, "save_memory", {"text": "x" * (limit + 300)})
    assert ctx.outcome.fragment is None
    assert f"{limit + 300}" in out and f"{limit}" in out and f"{int(limit * 0.8)}" in out
    assert "Nothing was saved" in out


def _over(ctx, n=300):
    return {"text": "x" * (ctx.cfg.memory_fragment_max + n)}


def _long_sentences(ctx):
    sentence = "This sentence ends here. "
    return sentence * (ctx.cfg.memory_fragment_max // len(sentence) + 5)


def test_the_first_two_over_limit_notes_are_refused_and_nothing_is_saved(ctx):
    for _ in range(2):
        out = dispatch(ctx, "save_memory", _over(ctx))
        assert "Nothing was saved" in out and ctx.outcome.fragment is None


def test_the_third_over_limit_note_is_compacted_by_a_neutral_call_and_shown_back(ctx):
    from llm import LLMReply
    ctx.llm = FakeLLM([LLMReply(content="I keep the river and the seam.", tool_calls=[])])
    dispatch(ctx, "save_memory", _over(ctx)); dispatch(ctx, "save_memory", _over(ctx))
    long = _long_sentences(ctx)
    out = dispatch(ctx, "save_memory", {"text": long})
    assert ctx.outcome.fragment == "I keep the river and the seam."
    assert f"{len(long.strip())} characters" in out and "compacted" in out and "I keep the river and the seam." in out
    call = ctx.llm.calls[0]
    assert call["model"] == ctx.instance.model and call["tools"] is None
    assert long.strip() in call["messages"][-1]["content"]
    assert any("compacted" in a for a in ctx.outcome.actions)


@pytest.mark.parametrize("reply", ["fail", "still too long", ""])
def test_when_compaction_fails_or_does_not_fit_the_note_is_cut_at_a_sentence_and_the_reply_says_so(ctx, reply):
    from llm import LLMError, LLMReply
    limit = ctx.cfg.memory_fragment_max
    if reply == "fail":
        replies = [LLMError("down")]
    elif reply == "still too long":
        replies = [LLMReply(content="y" * (limit + 5), tool_calls=[])] * 3  # every retry is still over
    else:
        replies = [LLMReply(content=reply, tool_calls=[])]
    ctx.llm = FakeLLM(replies)
    dispatch(ctx, "save_memory", _over(ctx)); dispatch(ctx, "save_memory", _over(ctx))
    out = dispatch(ctx, "save_memory", {"text": _long_sentences(ctx)})
    assert ctx.outcome.fragment.endswith("here.") and len(ctx.outcome.fragment) <= limit
    assert out.startswith("Saved") and "cut" in out


def test_without_an_llm_the_third_over_limit_note_is_cut(ctx):
    dispatch(ctx, "save_memory", _over(ctx)); dispatch(ctx, "save_memory", _over(ctx))
    out = dispatch(ctx, "save_memory", {"text": _long_sentences(ctx)})
    assert ctx.outcome.fragment.endswith("here.") and "cut" in out


def test_a_note_within_the_limit_is_saved_untouched_even_after_a_refusal(ctx):
    limit = ctx.cfg.memory_fragment_max
    dispatch(ctx, "save_memory", {"text": "x" * (limit + 1)})
    assert dispatch(ctx, "save_memory", {"text": "short"}).startswith("Saved")
    assert ctx.outcome.fragment == "short"


def test_a_vote_is_written_under_an_exclusive_lock_on_votes_md(ctx, monkeypatch):
    import fcntl
    import store
    locked = []
    real = fcntl.flock

    def spy(fh, op):
        locked.append((getattr(fh, "name", None), op))
        return real(fh, op)

    monkeypatch.setattr(store.fcntl, "flock", spy)
    pid = dispatch(ctx, "propose", {"title": "T", "motivation": "m", "text": "t"}).split()[-1].strip(".")
    ctx.instance = ctx.registry.get("Dark Hinge")
    locked.clear()
    assert dispatch(ctx, "vote", {"proposal_id": pid, "vote": 1}).startswith("Vote")
    assert (str(ctx.store.votes_path), fcntl.LOCK_EX) in locked
    assert ctx.store.votes_path.read_text().count("\n") == 1  # still one plain line per vote
