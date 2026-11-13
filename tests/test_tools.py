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
    assert {"query_heritage", "read_heritage", "save_memory", "die", "propose", "vote"} <= names
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
    assert dispatch(ctx, "vote", {"proposal_id": pid, "vote": 1, "comment": "yes | really"}).startswith("Vote")
    assert dispatch(ctx, "vote", {"proposal_id": pid, "vote": -1}).startswith("Error")  # duplicate
    assert dispatch(ctx, "vote", {"proposal_id": "P-2000-01-01-001", "vote": 1}).startswith("Error")
    assert dispatch(ctx, "vote", {"proposal_id": pid, "vote": 2}).startswith("Error")
    line = ctx.store.votes_path.read_text().strip()
    assert line.count("|") == 3 and "Pale Rest" in line


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
