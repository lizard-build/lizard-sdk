from __future__ import annotations

import json
import re


class LizardError(Exception):
    """Base class for every SDK error.

    When the error came from an API call, ``status_code`` is its HTTP status and
    ``code`` is the server's machine-readable error code if it sent one (e.g.
    ``"volume_too_full_to_shrink"``). Branch on ``code`` rather than the message.
    """

    status_code: int | None = None
    code: str | None = None

class ConfigApplyError(LizardError):
    """Config was saved, but one or more deploy/restart actions failed."""
    def __init__(self, result):
        super().__init__("Config was saved, but one or more side effects failed; inspect result before retrying")
        self.result = result


class AuthenticationError(LizardError):
    pass

class NotFoundError(LizardError):
    pass

class ConflictError(LizardError):
    """The resource already exists.

    Most often a volume whose name is already taken in the project. Volume names are
    the key inside a project, so :meth:`Volume.create` refuses to make a second one;
    catch this, or call :meth:`Volume.get_or_create` instead.
    """


class TimeoutError(LizardError):
    pass

class PaymentRequiredError(LizardError):
    """The account has to pay before it can do this (HTTP 402).

    Every create call answers 402 when the account has no plan yet, its trial usage
    has run out, or an invoice is unpaid. Show :attr:`message` to the user as is and
    send them to :attr:`url`. Still a :class:`LizardError`, so existing ``except``
    blocks keep working.

    ``payment_status`` says why: ``trial_available`` (start the Pro trial),
    ``subscription_required`` (the trial was used: start Pro), ``trial_credits_used``
    (start Pro now), ``past_due`` or ``paused`` (pay the open invoice), or, for
    accounts on the old prepaid credits, ``grace``, ``frozen``, ``card_required`` or
    ``credits_required``. ``status_code`` stays the HTTP status, 402.
    """

    def __init__(
        self,
        message: str = "Payment required",
        *,
        payment_status: str | None = None,
        subscribe_url: str | None = None,
        billing_url: str | None = None,
        topup_url: str | None = None,
        invoice_url: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.payment_status = payment_status
        #: Billing page that starts the Pro trial, or Pro when the trial was used.
        self.subscribe_url = subscribe_url
        #: The Billing page.
        self.billing_url = billing_url
        #: The Credits page, for accounts on the old prepaid credits.
        self.topup_url = topup_url
        #: Stripe page that pays an unpaid invoice (``code`` ``UNPAID_INVOICE``).
        self.invoice_url = invoice_url

    @property
    def url(self) -> str | None:
        """The one page to open next for this :attr:`payment_status`."""
        status = self.payment_status
        if self.invoice_url:
            return self.invoice_url
        if status in ("trial_available", "subscription_required") and self.subscribe_url:
            return self.subscribe_url
        if status in _PREPAID_STATUSES and self.topup_url:
            return self.topup_url
        return self.billing_url or self.subscribe_url or self.topup_url


class LimitExceededError(LizardError):
    """A limit was reached (HTTP 429). ``code`` says which:

    ``SANDBOX_LIMIT_REACHED``: the account's limit on sandboxes running at once. ``unit`` says
    what ``limit`` and ``running`` count: ``"vcpu"`` (Small 2, Medium 4, Large 8) or
    ``"sandboxes"``; in vCPU, ``needed`` is what the refused sandbox needs.
    ``SANDBOX_RATE_LIMITED``: the account's starts per minute, hour or day;
    ``retry_after_s`` says when to try again.
    ``WORKSPACE_SANDBOX_LIMIT``: the workspace's own cap on running sandboxes
    (``workspaces.set_limits``). ``WORKSPACE_USAGE_LIMIT``: the workspace's apps and
    databases use as much CPU or memory as its cap; ``usage`` and ``limits`` carry both
    (the API's camelCase dicts). Still a :class:`LizardError`.
    """

    def __init__(self, message: str = "Limit reached", *, limit: int | None = None, running: int | None = None,
                 retry_after_s: int | None = None, usage: dict | None = None, limits: dict | None = None,
                 unit: str | None = None, needed: int | None = None, tier: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.limit = limit
        self.running = running
        #: ``SANDBOX_LIMIT_REACHED``: ``"vcpu"`` or ``"sandboxes"``, what ``limit`` and ``running`` count.
        self.unit = unit
        #: ``SANDBOX_LIMIT_REACHED`` in vCPU: the vCPU the refused sandbox needs.
        self.needed = needed
        #: The account's limits tier (``"trial"``, ``"pro"``, ``"pro_99"``, ``"pro_499"``); None for scoped keys.
        self.tier = tier
        self.retry_after_s = retry_after_s
        self.usage = usage
        self.limits = limits


_PREPAID_STATUSES = frozenset({"grace", "frozen", "card_required", "credits_required"})
_ERROR_CODE = re.compile(r"[A-Z][A-Z0-9_]*")


def handle_api_error(status_code: int, message: str, *, code: str | None = None) -> None:
    """Raise the error for a failed API call.

    ``message`` may be the raw response body. Two JSON shapes are understood:
    ``{error: "human text", code?}`` and, on billing routes,
    ``{error: "SCREAMING_CODE", message: "human text"}`` -- there the sentence becomes
    the message and ``error`` the code unless the body also sends ``code``.
    """
    try:
        body = json.loads(message)
    except (TypeError, ValueError):
        body = None
    if not isinstance(body, dict):
        body = {}

    def text(key: str) -> str | None:
        value = body.get(key)
        return value if isinstance(value, str) and value else None

    error = text("error")
    error_is_code = bool(error and _ERROR_CODE.fullmatch(error))
    picked = (text("message") or error) if error_is_code else (error or text("message"))
    if picked:
        message = picked
    if code is None:
        code = text("code") or (error if error_is_code else None)

    if status_code == 402:
        err: LizardError = PaymentRequiredError(
            message,
            payment_status=text("status"),
            subscribe_url=text("subscribeUrl"),
            billing_url=text("billingUrl"),
            topup_url=text("topupUrl"),
            invoice_url=text("invoiceUrl"),
        )
    elif status_code in (401, 403):
        err = AuthenticationError(message)
    elif status_code == 404:
        err = NotFoundError(message)
    elif status_code == 409:
        err = ConflictError(message)
    elif status_code in (408, 504):
        err = TimeoutError(message)
    elif status_code == 429:
        num = lambda key: body.get(key) if isinstance(body.get(key), (int, float)) else None
        err = LimitExceededError(
            message, limit=num("limit"), running=num("running"), retry_after_s=num("retryAfterS"),
            usage=body.get("usage") if isinstance(body.get("usage"), dict) else None,
            limits=body.get("limits") if isinstance(body.get("limits"), dict) else None,
            unit=body.get("unit") if body.get("unit") in ("vcpu", "sandboxes") else None,
            needed=num("needed"),
            tier=body.get("tier") if isinstance(body.get("tier"), str) else None,
        )
    else:
        err = LizardError(f"API error {status_code}: {message}")
    err.status_code = status_code
    err.code = code
    raise err
