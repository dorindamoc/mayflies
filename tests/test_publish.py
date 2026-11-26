import json
import subprocess
import httpx
import pytest
from config import Config
from publish import Publisher, PublishError


def git(cwd, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd,
                          check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def pcfg(tmp_path):
    c = Config.from_env(home=tmp_path, env={"WEBSITE_PUBLISH": "true", "WEBSITE_REPO": "dorin/site",
                                            "WEBSITE_TOKEN": "sekret-token", "WEBSITE_DIR": str(tmp_path / "site")})
    for d in (c.memory_dir, c.state_dir, c.website_dir):
        d.mkdir(parents=True, exist_ok=True)
    git(c.website_dir, "init", "-b", "main")
    (c.website_dir / "index.html").write_text("home")
    git(c.website_dir, "add", "-A")
    git(c.website_dir, "commit", "-m", "start")
    return c


@pytest.fixture
def remote(tmp_path):
    path = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(path)], check=True, capture_output=True)
    return str(path)


def api(calls, status=201):
    def handler(req):
        calls.append((req.url.path, req.headers.get("authorization"), json.loads(req.content)))
        if status != 201:
            return httpx.Response(status, json={"message": "nope"})
        return httpx.Response(201, json={"html_url": "https://github.com/dorin/site/pull/7"})
    return httpx.MockTransport(handler)


def write(cfg, rel, text, author=None):
    p = cfg.website_dir / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    if author:
        f = cfg.state_dir / "website_authors.json"
        data = json.loads(f.read_text()) if f.exists() else {}
        data[rel] = author
        f.write_text(json.dumps(data))


def test_nothing_changed_opens_no_pr(pcfg, remote):
    calls = []
    assert Publisher(pcfg, push_url=remote, transport=api(calls)).publish_round() is None
    assert calls == []


def test_changes_become_one_pr_with_a_commit_per_author(pcfg, remote):
    calls = []
    write(pcfg, "art/poem.html", "<p>poem</p>", author="Pale Rest")
    write(pcfg, "art/two.html", "<p>two</p>", author="Pale Rest")
    write(pcfg, "teachings/a.html", "<p>a</p>", author="Dim Ebb")
    url = Publisher(pcfg, push_url=remote, transport=api(calls)).publish_round()
    assert url == "https://github.com/dorin/site/pull/7"
    path, auth, body = calls[0]
    assert path == "/repos/dorin/site/pulls" and auth == "Bearer sekret-token"
    assert body["base"] == "main" and body["head"].startswith("round-")
    assert "Pale Rest" in body["body"] and "art/poem.html" in body["body"] and "teachings/a.html" in body["body"]
    authors = git(pcfg.website_dir, "log", "--format=%an", "main", "-n", "2").split("\n")
    assert sorted(authors) == ["Dim Ebb", "Pale Rest"]
    assert git(pcfg.website_dir, "status", "--porcelain") == ""
    assert body["head"] in git(remote, "branch")


def test_file_without_a_known_author_is_the_schedulers(pcfg, remote):
    write(pcfg, "index.html", "edited by hand")
    Publisher(pcfg, push_url=remote, transport=api([])).publish_round()
    assert git(pcfg.website_dir, "log", "--format=%an", "-n", "1") == "Mayflies scheduler"


def test_unchanged_since_last_pr_opens_nothing_more(pcfg, remote):
    calls = []
    p = Publisher(pcfg, push_url=remote, transport=api(calls))
    write(pcfg, "a.html", "a", author="Pale Rest")
    p.publish_round()
    assert p.publish_round() is None
    assert len(calls) == 1


def test_next_round_pr_adds_only_new_work_on_top(pcfg, remote):
    calls = []
    p = Publisher(pcfg, push_url=remote, transport=api(calls))
    write(pcfg, "a.html", "a", author="Pale Rest")
    p.publish_round()
    write(pcfg, "b.html", "b", author="Dim Ebb")
    p.publish_round()
    assert len(calls) == 2 and calls[0][2]["head"] != calls[1][2]["head"]
    assert "b.html" in calls[1][2]["body"] and "a.html" not in calls[1][2]["body"]


def test_failed_pr_is_retried_next_round_for_the_same_work(pcfg, remote):
    write(pcfg, "a.html", "a", author="Pale Rest")
    with pytest.raises(PublishError):
        Publisher(pcfg, push_url=remote, transport=api([], status=500)).publish_round()
    calls = []
    url = Publisher(pcfg, push_url=remote, transport=api(calls)).publish_round()
    assert url and "a.html" in calls[0][2]["body"]


def test_failed_push_raises_without_leaking_the_token(pcfg, tmp_path):
    write(pcfg, "a.html", "a", author="Pale Rest")
    p = Publisher(pcfg, push_url=f"file://{tmp_path}/missing/sekret-token.git", transport=api([]))
    with pytest.raises(PublishError) as e:
        p.publish_round()
    assert "sekret-token" not in str(e.value)
    assert git(pcfg.website_dir, "status", "--porcelain") == ""  # the work is committed, waiting for a retry


def test_file_names_with_spaces_are_committed(pcfg, remote):
    write(pcfg, "art/my poem.html", "x", author="Pale Rest")
    Publisher(pcfg, push_url=remote, transport=api([])).publish_round()
    assert "art/my poem.html" in git(pcfg.website_dir, "ls-files")
