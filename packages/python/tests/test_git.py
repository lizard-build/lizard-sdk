"""lizard.git with the transport stubbed: where requests go and what they carry. No network."""
from __future__ import annotations

import json

import httpx
import pytest

import lizard as lz


def client(handler):
    git = lz.Lizard(api_key="liz_test", api_url="https://api.invalid", git_url="https://git.invalid/").git
    git.client._http = httpx.Client(base_url=git.client.url, headers={"X-API-Key": "liz_test"},
                                    transport=httpx.MockTransport(handler))
    return git


def test_key_goes_to_lizard_git():
    seen = []
    git = client(lambda req: (seen.append(req), httpx.Response(200, json={"login": "me"}))[1])
    assert git.me()["login"] == "me"
    assert str(seen[0].url) == "https://git.invalid/api/session"
    assert seen[0].headers["X-API-Key"] == "liz_test"


def test_list_pulls_and_repo_names():
    seen = []
    git = client(lambda req: (seen.append(req), httpx.Response(200, json={"items": [], "open": 0, "closed": 0}))[1])
    git.pulls.list("me/app", state="all")
    assert str(seen[0].url) == "https://git.invalid/api/repos/me/app/issues?state=all&pulls=1"
    with pytest.raises(ValueError):
        git.repos.get("noslash")


def test_file_query_has_path():
    seen = []
    git = client(lambda req: (seen.append(req), httpx.Response(200, json={"content": "x"}))[1])
    git.repos.file("me/app", "src/a b.py", ref="main")
    assert seen[0].url.params["path"] == "src/a b.py" and seen[0].url.params["ref"] == "main"


def test_commit_files_idempotency_header():
    seen = []
    git = client(lambda req: (seen.append(req), httpx.Response(201, json={"sha": "a" * 40}))[1])
    git.repos.commit_files("me/app", branch="main", message="m", files=[{"path": "a", "content": "x"}], idempotency_key="k1")
    assert seen[0].headers["Idempotency-Key"] == "k1"
    assert json.loads(seen[0].content) == {"branch": "main", "message": "m", "files": [{"path": "a", "content": "x"}]}


def test_branch_rule_fields_are_camel_case():
    seen = []
    git = client(lambda req: (seen.append(req), httpx.Response(201, json={"id": 1}))[1])
    git.branch_rules.create("me/app", "main", required_checks=["ci"], enforce_admins=True)
    assert json.loads(seen[0].content) == {"pattern": "main", "requiredChecks": ["ci"], "enforceAdmins": True}
    with pytest.raises(TypeError):
        git.branch_rules.create("me/app", "main", bogus=1)


def test_errors_map_to_sdk_errors():
    git = client(lambda req: httpx.Response(404, json={"error": "no such repository"}))
    with pytest.raises(lz.NotFoundError):
        git.repos.get("me/gone")


def test_clone_url():
    git = client(lambda req: httpx.Response(200))
    assert git.repos.clone_url("me/app") == "https://git.invalid/me/app.git"
    assert git.repos.clone_url("me/app", with_key=True) == "https://lizard:liz_test@git.invalid/me/app.git"
