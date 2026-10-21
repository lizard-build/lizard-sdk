"""Lizard Git (lizard.build/git): repositories, issues, pull requests, reviews, Actions-style
CI, releases, webhooks, branch protection and the rest, with the same API key as the rest of
the SDK. The key must be a whole account's (no scopes): Lizard Git refuses scoped keys.

Repositories are named ``"owner/name"``::

    lizard = Lizard()
    lizard.git.repos.create("app", private=True, readme=True)
    lizard.git.repos.commit_files("me/app", branch="main", message="Add CI",
        files=[{"path": ".lizard/workflows/ci.yml", "content": "on: push\\njobs: ..."}])
    pr = lizard.git.pulls.create("me/app", title="Feature", head="feature", base="main")
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Iterator
from urllib.parse import quote, urlencode, urlsplit, urlunsplit

import httpx

from ..config import HTTP_TIMEOUT_S, ConnectionConfig
from ..errors import handle_api_error

DEFAULT_GIT_URL = "https://lizard.build/git"

_REPO = re.compile(r"^([^/\s]+)/([^/\s]+?)(\.git)?$")
_ACTIVE = {"queued", "running", "waiting", "pending", "dispatched"}


def _seg(value: str) -> str:
    return quote(str(value), safe="")


def _path(value: str) -> str:
    """A branch or file path, each part escaped; . and .. parts refused (they'd reach other API paths)."""
    parts = value.split("/")
    if any(p in ("", ".", "..") for p in parts):
        raise ValueError(f'bad path: "{value}"')
    return "/".join(_seg(p) for p in parts)


def _qs(url: str, /, **values: Any) -> str:
    values = {k: (str(v).lower() if isinstance(v, bool) else v) for k, v in values.items() if v not in (None, "")}
    return url + ("?" + urlencode(values) if values else "")


def _repo(repo: str) -> str:
    m = _REPO.match(repo)
    if not m or m.group(1) in (".", "..") or m.group(2) in (".", ".."):
        raise ValueError(f'repository must be "owner/name", got "{repo}"')
    return f"/api/repos/{_seg(m.group(1))}/{_seg(m.group(2))}"


def _clean(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}


class GitClient:
    """HTTP to Lizard Git with the connection's API key."""

    def __init__(self, config: ConnectionConfig, url: str | None = None) -> None:
        self.config = config
        self.url = (url or os.environ.get("LIZARD_GIT_URL") or DEFAULT_GIT_URL).rstrip("/")
        self._http = httpx.Client(base_url=self.url, headers={"X-API-Key": config.api_key}, timeout=HTTP_TIMEOUT_S)

    def close(self) -> None:
        self._http.close()

    def raw(self, method: str, path: str, *, content: bytes | str | None = None, headers: dict | None = None) -> httpx.Response:
        res = self._http.request(method, path, content=content, headers=headers)
        if not res.is_success:
            handle_api_error(res.status_code, res.text)
        return res

    def request(self, method: str, path: str, body: Any = None, headers: dict | None = None) -> Any:
        h = dict(headers or {})
        content = None
        if body is not None:
            content = json.dumps(body)
            h["Content-Type"] = "application/json"
        res = self.raw(method, path, content=content, headers=h)
        return res.json() if res.status_code != 204 and res.content else None

    def get(self, path: str) -> Any:
        return self.request("GET", path)

    def post(self, path: str, body: Any = None) -> Any:
        return self.request("POST", path, {} if body is None else body)

    def put(self, path: str, body: Any = None) -> Any:
        return self.request("PUT", path, {} if body is None else body)

    def patch(self, path: str, body: Any) -> Any:
        return self.request("PATCH", path, body)

    def delete(self, path: str) -> Any:
        return self.request("DELETE", path)

    def bytes(self, path: str) -> bytes:
        return self.raw("GET", path).content


class GitReposAPI:
    def __init__(self, c: GitClient):
        self._c = c

    def list(self, *, owner: str | None = None, member: str | None = None, starred: str | None = None,
             q: str | None = None, sort: str | None = None) -> list[dict]:
        return self._c.get(_qs("/api/repos", owner=owner, member=member, starred=starred, q=q, sort=sort))

    def create(self, name: str, *, description: str | None = None, private: bool = False, readme: bool = False,
               default_branch: str | None = None) -> dict:
        """Answers the new repository's ``owner`` and ``name``."""
        return self._c.post("/api/repos", _clean({"name": name, "description": description, "private": private,
                                                   "readme": readme, "defaultBranch": default_branch}))

    def get(self, repo: str) -> dict:
        return self._c.get(_repo(repo))

    def update(self, repo: str, *, name: str | None = None, description: str | None = None,
               private: bool | None = None, default_branch: str | None = None, api_commits: bool | None = None) -> dict:
        """api_commits is accepted and ignored: every commit is made through the API now."""
        return self._c.patch(_repo(repo), _clean({"name": name, "description": description, "private": private,
                                                  "defaultBranch": default_branch, "apiCommits": api_commits}))

    def delete(self, repo: str) -> None:
        self._c.delete(_repo(repo))

    def star(self, repo: str) -> None:
        self._c.put(f"{_repo(repo)}/star")

    def unstar(self, repo: str) -> None:
        self._c.delete(f"{_repo(repo)}/star")

    def fork(self, repo: str, *, name: str | None = None) -> dict:
        """Fork into your account (``name`` defaults to the same name)."""
        return self._c.post(f"{_repo(repo)}/forks", _clean({"name": name}))

    def forks(self, repo: str) -> list[dict]:
        return self._c.get(f"{_repo(repo)}/forks")

    def refs(self, repo: str) -> list[dict]:
        """Branches and tags."""
        return self._c.get(f"{_repo(repo)}/refs")

    def create_branch(self, repo: str, name: str, from_ref: str | None = None) -> dict:
        return self._c.post(f"{_repo(repo)}/branches", _clean({"name": name, "from": from_ref}))

    def delete_branch(self, repo: str, name: str) -> None:
        self._c.delete(f"{_repo(repo)}/branches/{_path(name)}")

    def tree(self, repo: str, *, ref: str | None = None, path: str | None = None) -> dict:
        return self._c.get(_qs(f"{_repo(repo)}/tree", ref=ref, path=path))

    def file(self, repo: str, path: str, ref: str | None = None) -> dict:
        """A file as JSON (text in ``content``)."""
        return self._c.get(_qs(f"{_repo(repo)}/blob", path=path, ref=ref))

    def raw(self, repo: str, path: str, ref: str) -> bytes:
        """A file's bytes, whatever its size or type."""
        _repo(repo)
        owner, name = repo.split("/", 1)
        return self._c.bytes(f"/raw/{_seg(owner)}/{_seg(name)}/{_path(ref)}/{_path(path)}")

    def files(self, repo: str, ref: str | None = None) -> list[str]:
        """Every file path at a ref."""
        return self._c.get(_qs(f"{_repo(repo)}/files", ref=ref))

    def search(self, repo: str, q: str, ref: str | None = None) -> list[dict]:
        return self._c.get(_qs(f"{_repo(repo)}/search", q=q, ref=ref))

    def commits(self, repo: str, *, ref: str | None = None, path: str | None = None, page: int | None = None) -> dict:
        return self._c.get(_qs(f"{_repo(repo)}/commits", ref=ref, path=path, page=page))

    def commit(self, repo: str, sha: str) -> dict:
        return self._c.get(f"{_repo(repo)}/commits/{_seg(sha)}")

    def compare(self, repo: str, base: str, head: str) -> dict:
        return self._c.get(_qs(f"{_repo(repo)}/compare", base=base, head=head))

    def commit_files(self, repo: str, *, branch: str, message: str, files: list[dict], expect: str | None = None,
                     create_from: str | None = None, idempotency_key: str | None = None) -> dict:
        """Commit files on the server: no clone, no push (every commit to Lizard Git is made this way).
        With ``expect``, a branch that moved since is the server's to resolve (other files on the
        new tip, the same files merged line by line); only a real conflict raises (409).

        Each file is ``{"path", "content"}`` (``"base64": True`` for bytes), ``{"path", "delete": True}``
        or ``{"path", "moveFrom"}``. ``expect`` is the commit the branch must still point at (a moved
        branch raises ConflictError). The same ``idempotency_key`` gives the same result on a retry.
        """
        body = _clean({"branch": branch, "message": message, "files": files, "expect": expect, "createFrom": create_from})
        return self._c.request("POST", f"{_repo(repo)}/commits", body,
                               {"Idempotency-Key": idempotency_key} if idempotency_key else None)

    def land(self, repo: str, *, head: str, onto: str, delete_head: bool = False) -> dict:
        """Rebase ``head`` (branch or commit) onto ``onto`` on the server and move ``onto`` there."""
        return self._c.post(f"{_repo(repo)}/land", {"head": head, "onto": onto, "deleteHead": delete_head})

    def reflog(self, repo: str, ref: str | None = None) -> list[dict]:
        """Who moved which branch, when."""
        return self._c.get(_qs(f"{_repo(repo)}/reflog", ref=ref))

    def archive(self, repo: str, ref: str, format: str = "tar.gz") -> bytes:
        return self._c.bytes(f"{_repo(repo)}/archive/{_seg(ref)}.{format}")

    def clone_url(self, repo: str, *, with_key: bool = False) -> str:
        """Deprecated: Lizard Git no longer serves the git protocol (this address answers 410). Read
        with tree/file/raw/archive, write with commit_files, check out with ``lizard git clone``."""
        _repo(repo)
        u = urlsplit(f"{self._c.url}/{re.sub(r'[.]git$', '', repo)}.git")
        if with_key:
            u = u._replace(netloc=f"lizard:{_seg(self._c.config.api_key)}@{u.netloc}")
        return urlunsplit(u)


class _IssuesBase:
    _pulls = False

    def __init__(self, c: GitClient):
        self._c = c

    def _base(self, repo: str) -> str:
        return f"{_repo(repo)}/issues"

    def list(self, repo: str, *, state: str | None = None, q: str | None = None, label: str | None = None,
             assignee: str | None = None) -> dict:
        """``{"items": [...], "open": n, "closed": n}``; state is open (default), closed or all."""
        return self._c.get(_qs(self._base(repo), state=state, q=q, label=label, assignee=assignee,
                               pulls=1 if self._pulls else None))

    def get(self, repo: str, number: int) -> dict:
        """``{"issue", "comments", "canEdit", "canMerge", "pull"?}``."""
        return self._c.get(f"{self._base(repo)}/{number}")

    def update(self, repo: str, number: int, *, title: str | None = None, body: str | None = None,
               state: str | None = None, labels: list[str] | None = None, assignees: list[str] | None = None,
               reviewers: list[str] | None = None, draft: bool | None = None) -> dict:
        return self._c.patch(f"{self._base(repo)}/{number}", _clean({
            "title": title, "body": body, "state": state, "labels": labels, "assignees": assignees,
            "reviewers": reviewers, "draft": draft}))

    def comment(self, repo: str, number: int, body: str) -> dict:
        return self._c.post(f"{self._base(repo)}/{number}/comments", {"body": body})

    def close(self, repo: str, number: int) -> dict:
        return self.update(repo, number, state="closed")

    def reopen(self, repo: str, number: int) -> dict:
        return self.update(repo, number, state="open")


class GitIssuesAPI(_IssuesBase):
    def create(self, repo: str, *, title: str, body: str | None = None) -> dict:
        """Answers ``{"number": n}``."""
        return self._c.post(self._base(repo), _clean({"title": title, "body": body}))


class GitPullsAPI(_IssuesBase):
    _pulls = True

    def create(self, repo: str, *, title: str, head: str, base: str | None = None, body: str | None = None,
               head_repo: str | None = None, draft: bool = False, reviewers: list[str] | None = None) -> dict:
        """``head`` is a branch here, or ``"owner:branch"`` of a fork. Answers ``{"number": n}``."""
        return self._c.post(self._base(repo), _clean({"title": title, "head": head, "base": base, "body": body,
                                                       "headRepo": head_repo, "draft": draft, "reviewers": reviewers}))

    def ready(self, repo: str, number: int) -> dict:
        """Mark a draft ready for review."""
        return self.update(repo, number, draft=False)

    def merge(self, repo: str, number: int, *, method: str | None = None, message: str | None = None,
              delete_branch: bool = False, bypass: bool = False) -> dict:
        """method: merge (default), squash or rebase."""
        return self._c.post(f"{_repo(repo)}/pulls/{number}/merge", _clean({
            "method": method, "message": message, "deleteBranch": delete_branch, "bypass": bypass}))

    def diff(self, repo: str, number: int) -> dict:
        return self._c.get(f"{_repo(repo)}/pulls/{number}/diff")

    def commits(self, repo: str, number: int) -> list[dict]:
        return self._c.get(f"{_repo(repo)}/pulls/{number}/commits")

    def reviews(self, repo: str, number: int) -> dict:
        return self._c.get(f"{_repo(repo)}/pulls/{number}/reviews")

    def review(self, repo: str, number: int, *, event: str, body: str = "", comments: list[dict] | None = None) -> dict:
        """event: APPROVE, REQUEST_CHANGES or COMMENT; comments: ``{"path", "line", "side"?, "body"}``."""
        return self._c.post(f"{_repo(repo)}/pulls/{number}/reviews", _clean({"event": event, "body": body, "comments": comments}))

    def approve(self, repo: str, number: int, body: str = "") -> dict:
        return self.review(repo, number, event="APPROVE", body=body)

    def request_changes(self, repo: str, number: int, body: str) -> dict:
        return self.review(repo, number, event="REQUEST_CHANGES", body=body)

    def line_comment(self, repo: str, number: int, *, path: str, line: int, body: str, side: str = "RIGHT") -> dict:
        return self._c.post(f"{_repo(repo)}/pulls/{number}/comments", {"path": path, "line": line, "side": side, "body": body})

    def delete_line_comment(self, repo: str, number: int, comment_id: int) -> None:
        self._c.delete(f"{_repo(repo)}/pulls/{number}/comments/{comment_id}")

    def checks(self, repo: str, number: int) -> dict:
        """The combined commit status of the pull request's head (CI and external checks)."""
        sha = (self.get(repo, number).get("pull") or {}).get("headSha")
        if not sha:
            raise ValueError(f"pull request #{number} has no head commit")
        return self._c.get(f"{_repo(repo)}/commits/{sha}/status")


class GitSecretsAPI:
    def __init__(self, c: GitClient):
        self._c = c

    def list(self, repo: str) -> dict:
        return self._c.get(f"{_repo(repo)}/actions/secrets")

    def set(self, repo: str, name: str, value: str) -> None:
        self._c.put(f"{_repo(repo)}/actions/secrets/{_seg(name)}", {"value": value})

    def delete(self, repo: str, name: str) -> None:
        self._c.delete(f"{_repo(repo)}/actions/secrets/{_seg(name)}")


class GitVariablesAPI:
    def __init__(self, c: GitClient, base):
        self._c = c
        self._base = base

    def list(self, repo: str) -> dict:
        return self._c.get(f"{self._base(repo)}/variables")

    def set(self, repo: str, name: str, value: str) -> dict:
        return self._c.put(f"{self._base(repo)}/variables/{_seg(name)}", {"value": value})

    def delete(self, repo: str, name: str) -> None:
        self._c.delete(f"{self._base(repo)}/variables/{_seg(name)}")


class GitEnvironmentsAPI:
    """Environments: deployment protection rules, their secrets and variables (admins)."""

    def __init__(self, c: GitClient):
        self._c = c

    def _path(self, repo: str, env: str) -> str:
        return f"{_repo(repo)}/actions/environments/{_seg(env)}"

    def list(self, repo: str) -> dict:
        return self._c.get(f"{_repo(repo)}/actions/environments")

    def get(self, repo: str, env: str) -> dict:
        return self._c.get(self._path(repo, env))

    def set(self, repo: str, env: str, *, reviewers: list[str] | None = None, prevent_self_review: bool | None = None,
            wait_minutes: int | None = None, branch_policy: str | None = None, branches: list[str] | None = None) -> dict:
        """Create it, or change its rules (arguments left out stay). branch_policy: all, protected or custom."""
        return self._c.put(self._path(repo, env), _clean({"reviewers": reviewers, "preventSelfReview": prevent_self_review,
                                                          "waitMinutes": wait_minutes, "branchPolicy": branch_policy, "branches": branches}))

    def delete(self, repo: str, env: str) -> None:
        self._c.delete(self._path(repo, env))

    def list_secrets(self, repo: str, env: str) -> dict:
        return self._c.get(f"{self._path(repo, env)}/secrets")

    def set_secret(self, repo: str, env: str, name: str, value: str) -> dict:
        return self._c.put(f"{self._path(repo, env)}/secrets/{_seg(name)}", {"value": value})

    def delete_secret(self, repo: str, env: str, name: str) -> None:
        self._c.delete(f"{self._path(repo, env)}/secrets/{_seg(name)}")

    def variables(self, env: str) -> GitVariablesAPI:
        return GitVariablesAPI(self._c, lambda repo: self._path(repo, env))


class GitActionsAPI:
    def __init__(self, c: GitClient):
        self._c = c
        self.secrets = GitSecretsAPI(c)
        #: Repository variables: vars.NAME in every job.
        self.variables = GitVariablesAPI(c, lambda repo: f"{_repo(repo)}/actions")

    def deployments(self, repo: str, number: int) -> dict:
        """A run's jobs that deploy to an environment, and what each waits for."""
        return self._c.get(f"{_repo(repo)}/actions/runs/{number}/deployments")

    def review_deployments(self, repo: str, number: int, *, state: str, environments: list[str] | None = None,
                           comment: str | None = None) -> dict:
        """state: approved or rejected; environments: those named (default: all you may review)."""
        return self._c.post(f"{_repo(repo)}/actions/runs/{number}/deployments",
                            _clean({"state": state, "environments": environments, "comment": comment}))

    def runs(self, repo: str, *, branch: str | None = None, sha: str | None = None, workflow: str | None = None,
             status: str | None = None, pr: int | None = None, page: int | None = None) -> dict:
        return self._c.get(_qs(f"{_repo(repo)}/actions/runs", branch=branch, sha=sha, workflow=workflow,
                               status=status, pr=pr, page=page))

    def run(self, repo: str, number: int) -> dict:
        return self._c.get(f"{_repo(repo)}/actions/runs/{number}")

    def cancel(self, repo: str, number: int) -> None:
        self._c.post(f"{_repo(repo)}/actions/runs/{number}/cancel")

    def rerun(self, repo: str, number: int) -> dict:
        """The same workflow at the same commit again; answers the new run's ``number``."""
        return self._c.post(f"{_repo(repo)}/actions/runs/{number}/rerun")

    def approve(self, repo: str, number: int) -> None:
        """Let a run from a fork's pull request start."""
        self._c.post(f"{_repo(repo)}/actions/runs/{number}/approve")

    def log(self, repo: str, job_id: int, offset: int = 0) -> dict:
        """Part of a job's log from ``offset``: ``{"text", "next", "size", "done"}``."""
        return self._c.get(_qs(f"{_repo(repo)}/actions/jobs/{job_id}/log", offset=offset))

    def full_log(self, repo: str, job_id: int) -> str:
        return self._c.bytes(f"{_repo(repo)}/actions/jobs/{job_id}/log.txt").decode("utf-8", "replace")

    def follow_log(self, repo: str, job_id: int, *, interval: float = 1.5) -> Iterator[str]:
        """Each new piece of the log as it's written, until the job ends."""
        offset = 0
        while True:
            chunk = self.log(repo, job_id, offset)
            if chunk["text"]:
                yield chunk["text"]
            offset = chunk["next"]
            if chunk["done"] and offset >= chunk["size"]:
                return
            if not chunk["text"]:
                time.sleep(interval)

    def wait(self, repo: str, number: int, *, timeout: float = 1800, interval: float = 3) -> dict:
        """Wait until the run ends (success, failure, cancelled, ...)."""
        until = time.monotonic() + timeout
        while True:
            run = self.run(repo, number)
            if run["status"] not in _ACTIVE:
                return run
            if time.monotonic() > until:
                raise TimeoutError(f"run {number} is still {run['status']}")
            time.sleep(interval)

    def artifacts(self, repo: str, number: int) -> list[dict]:
        return self._c.get(f"{_repo(repo)}/actions/runs/{number}/artifacts")

    def download_artifact(self, repo: str, number: int, name: str) -> bytes:
        """An artifact as a .tar.gz."""
        return self._c.bytes(f"{_repo(repo)}/actions/runs/{number}/artifacts/{_seg(name)}")

    def workflows(self, repo: str) -> dict:
        return self._c.get(f"{_repo(repo)}/actions/workflows")

    def dispatch(self, repo: str, *, workflow: str, ref: str | None = None, inputs: dict[str, str] | None = None) -> dict:
        """Start a workflow that has ``on: workflow_dispatch``; answers the run's ``number``."""
        return self._c.post(f"{_repo(repo)}/actions/workflows/dispatch", _clean({"workflow": workflow, "ref": ref, "inputs": inputs}))

    def status(self, repo: str, shas: list[str]) -> dict:
        """Latest run status per commit."""
        return self._c.get(_qs(f"{_repo(repo)}/actions/status", shas=",".join(shas)))


class GitCollaboratorsAPI:
    def __init__(self, c: GitClient):
        self._c = c

    def list(self, repo: str) -> dict:
        return self._c.get(f"{_repo(repo)}/collaborators")

    def invite(self, repo: str, login: str, role: str = "write") -> dict:
        """role: read, write or admin. They're in once they accept."""
        return self._c.post(f"{_repo(repo)}/collaborators", {"login": login, "role": role})

    def set_role(self, repo: str, login: str, role: str) -> dict:
        return self._c.patch(f"{_repo(repo)}/collaborators/{_seg(login)}", {"role": role})

    def remove(self, repo: str, login: str) -> None:
        """Remove someone (or yourself: leave)."""
        self._c.delete(f"{_repo(repo)}/collaborators/{_seg(login)}")

    def cancel_invitation(self, repo: str, invitation_id: int) -> None:
        self._c.delete(f"{_repo(repo)}/invitations/{invitation_id}")

    def invitations(self) -> list[dict]:
        """Invitations waiting for you."""
        return self._c.get("/api/user/invitations")

    def accept(self, invitation_id: int) -> None:
        self._c.post(f"/api/user/invitations/{invitation_id}/accept")

    def decline(self, invitation_id: int) -> None:
        self._c.post(f"/api/user/invitations/{invitation_id}/decline")


class GitWebhooksAPI:
    def __init__(self, c: GitClient):
        self._c = c

    def list(self, repo: str) -> dict:
        return self._c.get(f"{_repo(repo)}/hooks")

    def create(self, repo: str, *, url: str, secret: str | None = None, events: list[str] | None = None,
               content_type: str | None = None, active: bool | None = None) -> dict:
        """GitHub-style payloads, signed with ``X-Hub-Signature-256`` when there's a secret."""
        return self._c.post(f"{_repo(repo)}/hooks", _clean({"url": url, "secret": secret, "events": events,
                                                             "contentType": content_type, "active": active}))

    def get(self, repo: str, hook_id: int) -> dict:
        return self._c.get(f"{_repo(repo)}/hooks/{hook_id}")

    def update(self, repo: str, hook_id: int, *, url: str | None = None, secret: str | None = None,
               events: list[str] | None = None, content_type: str | None = None, active: bool | None = None) -> dict:
        return self._c.patch(f"{_repo(repo)}/hooks/{hook_id}", _clean({"url": url, "secret": secret, "events": events,
                                                                         "contentType": content_type, "active": active}))

    def delete(self, repo: str, hook_id: int) -> None:
        self._c.delete(f"{_repo(repo)}/hooks/{hook_id}")

    def ping(self, repo: str, hook_id: int) -> None:
        self._c.post(f"{_repo(repo)}/hooks/{hook_id}/pings")

    def deliveries(self, repo: str, hook_id: int) -> list[dict]:
        return self._c.get(f"{_repo(repo)}/hooks/{hook_id}/deliveries")

    def delivery(self, repo: str, hook_id: int, delivery_id: int) -> dict:
        return self._c.get(f"{_repo(repo)}/hooks/{hook_id}/deliveries/{delivery_id}")

    def redeliver(self, repo: str, hook_id: int, delivery_id: int) -> None:
        self._c.post(f"{_repo(repo)}/hooks/{hook_id}/deliveries/{delivery_id}/redeliver")


_RULE_FIELDS = {"pattern": "pattern", "require_pull_request": "requirePullRequest", "required_approvals": "requiredApprovals",
                "required_checks": "requiredChecks", "block_force_push": "blockForcePush", "block_deletion": "blockDeletion",
                "enforce_admins": "enforceAdmins", "require_code_owners": "requireCodeOwners"}


class GitBranchRulesAPI:
    def __init__(self, c: GitClient):
        self._c = c

    @staticmethod
    def _body(kw: dict) -> dict:
        bad = set(kw) - set(_RULE_FIELDS)
        if bad:
            raise TypeError(f"unknown branch rule fields: {', '.join(sorted(bad))}")
        return {_RULE_FIELDS[k]: v for k, v in kw.items() if v is not None}

    def list(self, repo: str) -> list[dict]:
        return self._c.get(f"{_repo(repo)}/branch-rules")

    def create(self, repo: str, pattern: str, **rule: Any) -> dict:
        """rule: require_pull_request, required_approvals, required_checks, block_force_push,
        block_deletion, enforce_admins, require_code_owners."""
        return self._c.post(f"{_repo(repo)}/branch-rules", self._body({"pattern": pattern, **rule}))

    def update(self, repo: str, rule_id: int, **rule: Any) -> dict:
        return self._c.patch(f"{_repo(repo)}/branch-rules/{rule_id}", self._body(rule))

    def delete(self, repo: str, rule_id: int) -> None:
        self._c.delete(f"{_repo(repo)}/branch-rules/{rule_id}")


class GitLabelsAPI:
    def __init__(self, c: GitClient):
        self._c = c

    def list(self, repo: str) -> list[dict]:
        return self._c.get(f"{_repo(repo)}/labels")

    def create(self, repo: str, name: str, *, color: str | None = None, description: str | None = None) -> dict:
        return self._c.post(f"{_repo(repo)}/labels", _clean({"name": name, "color": color, "description": description}))

    def update(self, repo: str, name: str, *, new_name: str | None = None, color: str | None = None,
               description: str | None = None) -> dict:
        return self._c.patch(f"{_repo(repo)}/labels/{_seg(name)}", _clean({"name": new_name, "color": color, "description": description}))

    def delete(self, repo: str, name: str) -> None:
        self._c.delete(f"{_repo(repo)}/labels/{_seg(name)}")


class GitReleasesAPI:
    def __init__(self, c: GitClient):
        self._c = c

    def list(self, repo: str) -> list[dict]:
        return self._c.get(f"{_repo(repo)}/releases")

    def create(self, repo: str, tag: str, *, target: str | None = None, name: str | None = None, body: str | None = None,
               draft: bool = False, prerelease: bool = False) -> dict:
        """Creates the tag too when it doesn't exist (at ``target``, the default branch by default)."""
        return self._c.post(f"{_repo(repo)}/releases", _clean({"tag": tag, "target": target, "name": name, "body": body,
                                                                "draft": draft, "prerelease": prerelease}))

    def get(self, repo: str, release_id: int) -> dict:
        return self._c.get(f"{_repo(repo)}/releases/{release_id}")

    def get_by_tag(self, repo: str, tag: str) -> dict:
        return self._c.get(f"{_repo(repo)}/releases/tags/{_seg(tag)}")

    def update(self, repo: str, release_id: int, *, name: str | None = None, body: str | None = None,
               draft: bool | None = None, prerelease: bool | None = None) -> dict:
        return self._c.patch(f"{_repo(repo)}/releases/{release_id}", _clean({"name": name, "body": body, "draft": draft,
                                                                               "prerelease": prerelease}))

    def delete(self, repo: str, release_id: int) -> None:
        self._c.delete(f"{_repo(repo)}/releases/{release_id}")

    def upload_asset(self, repo: str, release_id: int, name: str, data: bytes | str,
                     content_type: str = "application/octet-stream") -> dict:
        res = self._c.raw("POST", _qs(f"{_repo(repo)}/releases/{release_id}/assets", name=name), content=data,
                          headers={"Content-Type": content_type})
        return res.json()

    def download_asset(self, repo: str, release_id: int, asset_id: int) -> bytes:
        return self._c.bytes(f"{_repo(repo)}/releases/{release_id}/assets/{asset_id}")

    def delete_asset(self, repo: str, release_id: int, asset_id: int) -> None:
        self._c.delete(f"{_repo(repo)}/releases/{release_id}/assets/{asset_id}")


class GitStatusesAPI:
    def __init__(self, c: GitClient):
        self._c = c

    def create(self, repo: str, sha: str, *, state: str, context: str, description: str | None = None,
               target_url: str | None = None) -> dict:
        """state: pending, success, failure or error (what required checks in branch rules wait for)."""
        return self._c.post(f"{_repo(repo)}/statuses/{_seg(sha)}", _clean({
            "state": state, "context": context, "description": description, "target_url": target_url}))

    def list(self, repo: str, ref: str) -> list[dict]:
        return self._c.get(f"{_repo(repo)}/commits/{_seg(ref)}/statuses")

    def combined(self, repo: str, ref: str) -> dict:
        return self._c.get(f"{_repo(repo)}/commits/{_seg(ref)}/status")


class GitNotificationsAPI:
    def __init__(self, c: GitClient):
        self._c = c

    def list(self, *, all: bool = False) -> dict:
        return self._c.get(_qs("/api/notifications", all=1 if all else None))

    def mark_read(self, ids: list[int] | None = None) -> None:
        self._c.post("/api/notifications/read", {"ids": ids} if ids else {"all": True})


class GitTokensAPI:
    def __init__(self, c: GitClient):
        self._c = c

    def list(self) -> list[dict]:
        return self._c.get("/api/user/tokens")

    def create(self, name: str, *, repos: list[str] | None = None, refs: list[str] | None = None,
               paths: list[str] | None = None, read_only: bool = False) -> dict:
        """A Lizard Git token (lzg_...), optionally limited; the secret is in ``token``, once."""
        return self._c.post("/api/user/tokens", _clean({"name": name, "repos": repos, "refs": refs, "paths": paths,
                                                         "readOnly": read_only}))

    def delete(self, token_id: int) -> None:
        self._c.delete(f"/api/user/tokens/{token_id}")


class GitAPI:
    """``lizard.git``: everything Lizard Git does, with the client's API key."""

    def __init__(self, config: ConnectionConfig, url: str | None = None):
        c = self.client = GitClient(config, url)
        self.repos = GitReposAPI(c)
        self.issues = GitIssuesAPI(c)
        self.pulls = GitPullsAPI(c)
        self.actions = GitActionsAPI(c)
        self.environments = GitEnvironmentsAPI(c)
        self.collaborators = GitCollaboratorsAPI(c)
        self.webhooks = GitWebhooksAPI(c)
        self.branch_rules = GitBranchRulesAPI(c)
        self.labels = GitLabelsAPI(c)
        self.releases = GitReleasesAPI(c)
        self.statuses = GitStatusesAPI(c)
        self.notifications = GitNotificationsAPI(c)
        self.tokens = GitTokensAPI(c)

    def me(self) -> dict:
        """Who the key signs in as on Lizard Git."""
        return self.client.get("/api/session")

    def user(self, login: str) -> dict:
        return self.client.get(f"/api/users/{_seg(login)}")
