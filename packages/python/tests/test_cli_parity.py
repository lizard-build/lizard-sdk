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

    def read(self) -> bytes:
        return self.content

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


def test_subscription_is_parsed(calls):
    seed(calls, {"plan": "pro", "status": "trialing", "isOwner": False, "priceCents": 1900, "taxIncluded": True,
                 "includedCents": 1900,
                 "trial": {"eligible": False, "days": 7, "creditCents": 500, "promoCode": "ROST", "endsAt": 2,
                           "usedCents": 120, "remainingCents": 380},
                 "period": {"kind": "trial", "start": 1, "end": 2, "includedCents": 500, "usedCents": 120,
                            "overageCents": 0, "billedOverageCents": 0, "unbilledOverageCents": 0,
                            "nextOverageChargeAtCents": None},
                 "nextCharge": {"at": 2, "amountCents": 1900}, "cancelAt": None, "pastDue": False,
                 "openInvoiceUrl": None, "paymentMethod": None, "limits": {"tier": "trial", "replicasPerApp": 1},
                 "checkoutAvailable": True})
    sub = lz.Lizard(**KW).billing.subscription(workspace_id="w 1")
    assert calls[0]["url"] == "/api/billing/subscription?workspaceId=w+1"
    assert isinstance(sub, lz.Subscription)
    assert (sub.plan, sub.status, sub.is_owner) == ("pro", "trialing", False)
    assert sub.trial.remaining_cents == 380 and sub.trial.promo_code == "ROST"
    assert sub.period.kind == "trial" and sub.period.used_cents == 120
    assert sub.next_charge == {"at": 2, "amountCents": 1900}
    assert sub.limits == {"tier": "trial", "replicasPerApp": 1}


def test_subscription_without_a_plan(calls):
    seed(calls, {"plan": "none", "status": "none", "trial": {"eligible": True, "days": 7, "creditCents": 500},
                 "period": None, "nextCharge": None, "checkoutAvailable": True})
    sub = lz.Lizard(**KW).billing.subscription()
    assert calls[0]["url"] == "/api/billing/subscription"
    assert sub.period is None and sub.trial.eligible and sub.trial.days == 7


def test_checkout_start_now_cancel_resume(calls):
    seed(calls,
         {"url": "https://checkout.test/cs_1", "sessionId": "cs_1", "trialDays": 7, "trialCreditCents": 500},
         {"status": "requires_action", "invoiceUrl": "https://invoice.test/i"},
         {"cancelAt": 1791800000000},
         {"cancelAt": None})
    billing = lz.Lizard(**KW).billing
    session = billing.start_checkout()
    assert (session.url, session.session_id, session.trial_days, session.trial_credit_cents) == \
        ("https://checkout.test/cs_1", "cs_1", 7, 500)
    now = billing.start_pro_now()
    assert (now.status, now.invoice_url) == ("requires_action", "https://invoice.test/i")
    assert billing.cancel() == 1791800000000
    assert billing.resume() is None
    assert [(c["method"], c["url"], c["body"]) for c in calls] == [
        ("POST", "/api/billing/subscription/checkout", {}),
        ("POST", "/api/billing/subscription/start-now", {}),
        ("POST", "/api/billing/subscription/cancel", {}),
        ("POST", "/api/billing/subscription/resume", {}),
    ]


def test_promo_returns_the_trial(calls):
    seed(calls, {"status": "pending_payment_method", "code": "ROST", "creditCents": 10000, "expiresAt": None,
                 "balanceCents": 0, "trialDays": 31, "trialCreditCents": 10000, "appliesTo": "next_checkout"})
    out = lz.Lizard(**KW).billing.redeem_promo("ROST")
    assert isinstance(out, lz.PromoRedemption)
    assert (out.trial_days, out.trial_credit_cents, out.applies_to) == (31, 10000, "next_checkout")


def test_promo_from_an_older_server(calls):
    seed(calls, {"status": "applied", "creditCents": 2500, "expiresAt": None, "balanceCents": 3000})
    out = lz.Lizard(**KW).billing.redeem_promo("OLD")
    assert (out.credit_cents, out.balance_cents, out.trial_days, out.applies_to) == (2500, 3000, None, None)


def test_removed_billing_methods_are_gone():
    billing = lz.Lizard(**KW).billing
    for gone in ("purchase", "auto_topup", "set_auto_topup", "run_auto_topup", "x402_quote", "pay_x402",
                 "payment_status", "setup_payment_method"):
        assert not hasattr(billing, gone)


def test_transactions_query_is_built_from_options(calls):
    seed(calls, {"items": [], "nextCursor": None})
    lz.Lizard(**KW).billing.transactions(limit=5, include_usage=True)
    assert calls[0]["url"] == "/api/billing/transactions?limit=5&includeUsage=1"


# ── volume resize ─────────────────────────────────────────────────────────────

_VOL = {"id": "v1", "projectId": "p1", "name": "my data", "sizeGb": 20,
        "status": "ready", "createdAt": 1, "sizeEnforced": True}


def test_volume_resize_patches_by_encoded_name(calls):
    seed(calls, _VOL)
    info = lz.Volume.resize("p1", "my data/x", 20, **KW)
    assert len(calls) == 1
    assert calls[0]["method"] == "PATCH"
    assert calls[0]["url"] == f"{API}/api/projects/p1/volumes/my%20data%2Fx"
    assert calls[0]["body"] == {"sizeGb": 20}
    assert isinstance(info, lz.VolumeInfo)
    assert info.size_gb == 20
    assert info.size_enforced is True


def test_volume_resize_to_on_a_held_volume(calls):
    seed(calls, _VOL)
    info = lz.Volume("v1", name="data", **KW).resize_to("p1", 3)
    assert calls[0]["method"] == "PATCH"
    assert calls[0]["url"] == f"{API}/api/projects/p1/volumes/v1"
    assert calls[0]["body"] == {"sizeGb": 3}
    assert info.id == "v1"


def test_project_bound_volumes_resize(calls):
    seed(calls, [{"id": "p_rsz", "name": "rsz-proj", "slug": "rsz-proj"}], _VOL)
    lz.Lizard(project="rsz-proj", **KW).volumes.resize("scratch", 12)
    assert calls[-1]["method"] == "PATCH"
    assert calls[-1]["url"] == f"{API}/api/projects/p_rsz/volumes/scratch"
    assert calls[-1]["body"] == {"sizeGb": 12}


def test_volume_resize_keeps_the_error_code(calls):
    seed(calls, ({"error": "Volume too full to shrink", "code": "volume_too_full_to_shrink"}, 409))
    with pytest.raises(lz.ConflictError) as ei:
        lz.Volume.resize("p1", "data", 1, **KW)
    assert ei.value.code == "volume_too_full_to_shrink"
    assert ei.value.status_code == 409
    assert str(ei.value) == "Volume too full to shrink"


def test_volume_resize_timeout_is_timeout_error_with_code(calls):
    seed(calls, ({"error": "Resize timed out", "code": "volume_resize_timeout"}, 504))
    with pytest.raises(lz.TimeoutError) as ei:
        lz.Volume.resize("p1", "data", 50, **KW)
    assert ei.value.code == "volume_resize_timeout"


def test_platform_client_errors_keep_the_code_too(calls):
    seed(calls, ({"error": "No capacity", "code": "volume_capacity_unavailable"}, 503))
    with pytest.raises(lz.LizardError) as ei:
        lz.Lizard(**KW).regions.list()
    assert ei.value.code == "volume_capacity_unavailable"
    assert ei.value.status_code == 503
    assert "No capacity" in str(ei.value)


# ── payment required (HTTP 402) ───────────────────────────────────────────────

_PAY = {
    "error": "INSUFFICIENT_CREDITS",
    "code": "PAYMENT_REQUIRED",
    "status": "trial_available",
    "message": "Start your 7-day Pro trial with $5 in credits to deploy. No charge today, then $19/month.",
    "subscribeUrl": "https://lizard.build/profile/account-billing?subscribe=1",
    "billingUrl": "https://lizard.build/profile/account-billing",
    "topupUrl": "https://lizard.build/profile/account-credits",
    "balanceCents": 0,
    "availableCents": 100,
}


def test_402_is_payment_required_with_the_links(calls):
    seed(calls, (_PAY, 402))
    with pytest.raises(lz.PaymentRequiredError) as ei:
        lz.Lizard(**KW).projects.create(workspace_id="w1", name="x")
    err = ei.value
    assert isinstance(err, lz.LizardError)
    assert err.status_code == 402
    assert err.code == "PAYMENT_REQUIRED"
    assert err.message == _PAY["message"] == str(err)
    assert err.payment_status == "trial_available"
    assert err.subscribe_url == _PAY["subscribeUrl"]
    assert err.billing_url == _PAY["billingUrl"]
    assert err.url == _PAY["subscribeUrl"]


def test_402_from_an_older_server(calls):
    seed(calls, ({"error": "INSUFFICIENT_CREDITS", "status": "frozen", "message": "Your credits are used up.",
                  "topupUrl": _PAY["topupUrl"]}, 402))
    with pytest.raises(lz.PaymentRequiredError) as ei:
        lz.Lizard(**KW).regions.list()
    assert ei.value.code == "INSUFFICIENT_CREDITS"
    assert ei.value.message == "Your credits are used up."
    assert ei.value.billing_url is None
    assert ei.value.url == _PAY["topupUrl"]


@pytest.mark.parametrize("status,url", [
    ("past_due", _PAY["billingUrl"]),
    ("trial_credits_used", _PAY["billingUrl"]),
    ("subscription_required", _PAY["subscribeUrl"]),
])
def test_402_points_at_the_right_page(calls, status, url):
    seed(calls, ({**_PAY, "status": status}, 402))
    with pytest.raises(lz.PaymentRequiredError) as ei:
        lz.Lizard(**KW).regions.list()
    assert ei.value.url == url


def test_402_unpaid_invoice_links_the_invoice(calls):
    seed(calls, ({"error": "UNPAID_INVOICE", "message": "Pay your open invoice before starting Pro again",
                  "invoiceUrl": "https://invoice.stripe.com/i/x"}, 402))
    with pytest.raises(lz.PaymentRequiredError) as ei:
        lz.Lizard(**KW).regions.list()
    assert ei.value.code == "UNPAID_INVOICE"
    assert ei.value.url == "https://invoice.stripe.com/i/x"


def test_coded_billing_errors_keep_sentence_and_code(calls):
    seed(calls, ({"error": "ALREADY_SUBSCRIBED", "message": "This account already has Pro"}, 409))
    with pytest.raises(lz.ConflictError) as ei:
        lz.Lizard(**KW).projects.create(workspace_id="w1", name="x")
    assert str(ei.value) == "This account already has Pro"
    assert ei.value.code == "ALREADY_SUBSCRIBED"
