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

    Every create call answers 402 when the account has no plan yet, its trial credits
    are used up, or an invoice is unpaid. Show :attr:`message` to the user as is and
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
    else:
        err = LizardError(f"API error {status_code}: {message}")
    err.status_code = status_code
    err.code = code
    raise err
