import pytest
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
    assert "too long" in dispatch(ctx, "save_memory", {"text": "z" * 501}).lower()
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
    assert '"id": "H-001"' in dispatch(ctx, "read_heritage", {})
    out = dispatch(ctx, "board_post", {})
    assert out.startswith("Error") and '"text"' in out


def test_add_heritage_accepts_a_string_for_tags(ctx):
    out = dispatch(ctx, "add_heritage", {"title": "T", "tags": "mud, water", "summary": "s", "body": "b"})
    assert "mud" in out and "water" in out
