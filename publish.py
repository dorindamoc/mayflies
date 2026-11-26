"""Opens a pull request on the website repo for the changes instances made in a round."""

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone

import httpx

from store import atomic_write

SCHEDULER = "Mayflies scheduler"
BODY_MAX = 6000


class PublishError(RuntimeError):
    pass


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "instance"


class Publisher:
    """Commits what instances wrote to the website (one commit per author), pushes a branch, opens a PR.

    Instances never touch git: they keep using write_website. The working copy stays where it is, so
    instances keep seeing their own unmerged pages; each PR is cut from the tip of the last one, so once
    earlier PRs are merged a new PR shows only the new work.
    """

    def __init__(self, cfg, push_url: str = None, transport=None, clock=None):
        self.cfg = cfg
        self.push_url = push_url or f"https://x-access-token:{cfg.website_token}@github.com/{cfg.website_repo}.git"
        self.transport = transport
        self.clock = clock or (lambda: datetime.now(tz=timezone.utc))

    # --- git plumbing ---
    def _redact(self, text: str) -> str:
        token = self.cfg.website_token
        return text.replace(token, "***") if token else text

    def _git(self, *args, env=None) -> str:
        import os
        cmd = ["git", "-c", "safe.directory=*", "-c", "commit.gpgsign=false", *args]
        try:
            done = subprocess.run(cmd, cwd=self.cfg.website_dir, capture_output=True, text=True,
                                  env={**os.environ, **(env or {})}, timeout=300)
        except (OSError, subprocess.SubprocessError) as e:
            raise PublishError(self._redact(f"git {args[0]} failed: {e}"))
        if done.returncode != 0:
            raise PublishError(self._redact(f"git {args[0]} failed: {done.stderr.strip() or done.stdout.strip()}"))
        return done.stdout

    def _changed(self) -> list:
        out = self._git("status", "--porcelain", "-z", "--untracked-files=all")
        paths, entries = [], out.split("\0")
        i = 0
        while i < len(entries):
            e = entries[i]
            if len(e) > 3:
                paths.append(e[3:])
                if e[0] in "RC":
                    i += 1  # a rename or copy lists its source next
            i += 1
        return paths

    def _authors(self) -> dict:
        try:
            return json.loads((self.cfg.state_dir / "website_authors.json").read_text())
        except (OSError, ValueError):
            return {}

    @property
    def _state_path(self):
        return self.cfg.state_dir / "publish.json"

    def _published(self):
        try:
            return json.loads(self._state_path.read_text())["published"]
        except (OSError, ValueError, KeyError, TypeError):
            return None

    # --- the round ---
    def _commit_by_author(self, paths: list) -> None:
        authors, groups = self._authors(), {}
        for p in paths:
            groups.setdefault(authors.get(p) or SCHEDULER, []).append(p)
        for author in sorted(groups):
            files = sorted(groups[author])
            self._git("add", "-A", "--", *files)
            msg = f"{author}: {len(files)} file(s)\n\n" + "\n".join(f"- {f}" for f in files)
            email = f"{_slug(author)}@mayflies.invalid"
            self._git("commit", "-m", msg, env={
                "GIT_AUTHOR_NAME": author, "GIT_AUTHOR_EMAIL": email,
                "GIT_COMMITTER_NAME": SCHEDULER, "GIT_COMMITTER_EMAIL": "scheduler@mayflies.invalid"})

    def _body(self, since: str) -> str:
        log = self._git("log", "--reverse", "--format=%an%x09%H", f"{since}..HEAD").strip().splitlines()
        lines = ["Pages instances wrote during the round, one commit per author.", ""]
        for row in log:
            author, sha = row.split("\t")
            files = self._git("diff-tree", "--no-commit-id", "--name-status", "-r", sha).strip().splitlines()
            lines.append(f"**{author}**")
            lines += [f"- `{f.split(chr(9), 1)[-1]}` ({f.split(chr(9))[0]})" for f in files]
            lines.append("")
        return "\n".join(lines)[:BODY_MAX]

    def publish_round(self):
        since = self._published()
        if since is None:  # first run: what is already committed is not this round's work
            since = self._git("rev-parse", "HEAD").strip()
            atomic_write(self._state_path, json.dumps({"published": since}))
        paths = self._changed()
        if paths:
            self._commit_by_author(paths)
        head = self._git("rev-parse", "HEAD").strip()
        if head == since:
            return None
        now = self.clock()
        branch = f"round-{now:%Y%m%d-%H%M%S}-{head[:7]}"
        body = self._body(since)
        self._git("push", self.push_url, f"HEAD:refs/heads/{branch}")
        count = int(self._git("rev-list", "--count", f"{since}..HEAD").strip())
        title = f"Website: round ending {now:%Y-%m-%d %H:%M} UTC ({count} commit{'s' if count != 1 else ''})"
        url = self._open_pr(branch, title, body)
        atomic_write(self._state_path, json.dumps({"published": head, "pr": url}))
        return url

    def _open_pr(self, branch: str, title: str, body: str) -> str:
        try:
            with httpx.Client(transport=self.transport, timeout=30) as client:
                r = client.post(f"https://api.github.com/repos/{self.cfg.website_repo}/pulls",
                                headers={"Authorization": f"Bearer {self.cfg.website_token}",
                                         "Accept": "application/vnd.github+json"},
                                json={"title": title, "head": branch, "base": self.cfg.website_base_branch,
                                      "body": body})
        except httpx.HTTPError as e:
            raise PublishError(self._redact(f"opening the pull request failed: {e}"))
        if r.status_code != 201:
            raise PublishError(self._redact(f"opening the pull request failed: {r.status_code} {r.text[:200]}"))
        return r.json()["html_url"]
