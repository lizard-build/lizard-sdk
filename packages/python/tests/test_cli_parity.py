"""The Python SDK is meant to reach everything `lizard` the CLI reaches.

These cover the pieces that were missing or wrong, with httpx stubbed -- no network.
"""
from __future__ import annotations

import json

import httpx
import pytest

import lizard as lz

API = "https://api.parity.invalid"
KW = {"api_key": "liz_test", "api_url": API}


class _Res:
    """Minimal httpx.Response stand-in, enough for what the SDK reads."""

    def __init__(self, body, status: int = 200):
        self._body = body
        self.status_code = status
        self.content = json.dumps(body).encode()

    @property
    def is_success(self) -> bool:
        return self.status_code < 400

    def json(self):
        return self._body

    @property
    def text(self) -> str:
        return json.dumps(self._body)


class _Recorder(list):
    """The recorded requests, plus the queue of responses to answer them with."""

    def __init__(self):
        super().__init__()
        self.queue: list[_Res] = []


@pytest.fixture
def calls(monkeypatch):
    """Record every request; answer each from a queue the test seeds."""
    recorded = _Recorder()

    def _record(method: str):
        def fn(url, *a, **kw):
            body = kw.get("json")
            if body is None and kw.get("content"):
                body = json.loads(kw["content"])
            recorded.append({"method": method, "url": str(url), "body": body})
            return recorded.queue[min(len(recorded) - 1, len(recorded.queue) - 1)]
        return fn

    for m in ("get", "post", "delete", "patch"):
        monkeypatch.setattr(httpx, m, _record(m.upper()))
        monkeypatch.setattr(
            httpx.Client, m,
            lambda self, url, *a, _m=m, **kw: _record(_m.upper())(url, *a, **kw),
        )

    return recorded


def seed(calls, *responses):
    calls.queue.extend(_Res(*r) if isinstance(r, tuple) else _Res(r) for r in responses)


# ── region ────────────────────────────────────────────────────────────────────

def test_volume_create_sends_region(calls):
    seed(calls, {"id": "v1", "name": "data"})
    lz.Volume.create("p1", "data", size_gb=3, region="us-east-1", **KW)
    assert calls[0]["body"]["region"] == "us-east-1"
    assert calls[0]["body"]["sizeGb"] == 3


def test_volume_get_or_create_sends_region(calls):
    seed(calls, {"id": "v1", "name": "data"})
    lz.Volume.get_or_create("p1", "data", region="eu-west-lim-a", **KW)
    assert calls[0]["body"]["region"] == "eu-west-lim-a"
    assert calls[0]["body"]["getOrCreate"] is True


def test_sandbox_create_sends_region(calls):
    seed(calls, {"sandboxId": "s1"})
    lz.Sandbox.create("codex", project_id="p1", region="us-east-1", **KW)
    assert calls[0]["body"]["region"] == "us-east-1"


def test_sandbox_create_omits_region_so_the_volume_decides(calls):
    seed(calls, {"sandboxId": "s1"})
    lz.Sandbox.create("codex", project_id="p1", volume_name="data", **KW)
    assert "region" not in calls[0]["body"]
    assert calls[0]["body"]["volumeName"] == "data"


# ── connect ───────────────────────────────────────────────────────────────────

def test_connect_reads_instead_of_resuming(calls):
    # resume is a hard 501 on every sandbox; connecting must not touch it.
    seed(calls, {"sandboxId": "s1", "template": "codex"})
    sb = lz.Sandbox.connect("s1", **KW)
    assert sb.sandbox_id == "s1"
    assert len(calls) == 1
    assert calls[0]["method"] == "GET"
    assert calls[0]["url"] == f"{API}/api/sandboxes/s1"
    assert "resume" not in calls[0]["url"]


def test_connect_propagates_404(calls):
    seed(calls, ({"error": "Sandbox not found"}, 404))
    with pytest.raises(lz.NotFoundError):
        lz.Sandbox.connect("gone", **KW)


# ── provisioning surfaces ─────────────────────────────────────────────────────

def test_workspace_create(calls):
    seed(calls, {"id": "w1", "name": "u-1", "slug": "u-1"})
    ws = lz.Lizard(**KW).workspaces.create(name="u-1")
    assert ws.id == "w1"
    assert calls[0]["method"] == "POST"
    assert calls[0]["body"] == {"name": "u-1"}


def test_workspace_delete_is_empty_only_by_default(calls):
    seed(calls, {})
    lz.Lizard(**KW).workspaces.delete("w1")
    assert calls[0]["url"] == "/api/workspaces/w1?requireEmpty=true"


def test_workspace_delete_force_drops_the_guard(calls):
    seed(calls, {})
    lz.Lizard(**KW).workspaces.delete("w1", force=True)
    assert calls[0]["url"] == "/api/workspaces/w1"


def test_api_key_scopes_fold_into_one_array(calls):
    seed(calls, {"id": "k1", "name": "k", "key": "liz_secret", "scopes": []})
    key = lz.Lizard(**KW).api_keys.create(name="k", workspaces=["w1"], projects=["p1"])
    assert key.key == "liz_secret"
    assert calls[0]["body"]["scopes"] == [
        {"type": "workspace", "id": "w1"},
        {"type": "project", "id": "p1"},
    ]


def test_regions_and_balance(calls):
    seed(calls, [{"id": "us-east-1"}], {"plan": "payg", "status": "active",
                                        "balanceCents": -5, "hourlyRateCents": 22})
    client = lz.Lizard(**KW)
    assert client.regions.list()[0].id == "us-east-1"
    assert client.billing.balance().hourly_rate_cents == 22


def test_transactions_query_is_built_from_options(calls):
    seed(calls, {"items": [], "nextCursor": None})
    lz.Lizard(**KW).billing.transactions(limit=5, include_usage=True)
    assert calls[0]["url"] == "/api/billing/transactions?limit=5&includeUsage=1"
