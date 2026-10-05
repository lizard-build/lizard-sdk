from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .client import PlatformClient


@dataclass
class Balance:
    """Prepaid credits balance: old credits accounts (``plan == "payg"``) until
    1 November 2026, and enterprise usage."""

    plan: str
    status: str
    #: Current balance in cents. Negative means the account is in debt.
    balance_cents: int
    #: Current burn rate in cents per hour, across every running workload.
    hourly_rate_cents: int
    #: Hours of runway left at the current rate, or None when nothing is running.
    runway_hours: float | None = None
    overdraft_limit_cents: int | None = None
    available_cents: int | None = None
    expiring_cents: int = 0
    email: str | None = None

    @classmethod
    def _from_dict(cls, d: dict) -> "Balance":
        return cls(
            plan=d.get("plan", ""),
            status=d.get("status", ""),
            balance_cents=int(d.get("balanceCents") or 0),
            hourly_rate_cents=int(d.get("hourlyRateCents") or 0),
            runway_hours=d.get("runwayHours"),
            overdraft_limit_cents=d.get("overdraftLimitCents"),
            available_cents=d.get("availableCents"),
            expiring_cents=int(d.get("expiringCents") or 0),
            email=d.get("email"),
        )


@dataclass
class Transaction:
    id: str
    kind: str
    amount_cents: int
    created_at: int
    balance_after_cents: int | None = None
    description: str | None = None

    @classmethod
    def _from_dict(cls, d: dict) -> "Transaction":
        return cls(
            id=d.get("id", ""),
            kind=d.get("kind", ""),
            amount_cents=int(d.get("amountCents") or 0),
            created_at=int(d.get("createdAt") or 0),
            balance_after_cents=d.get("balanceAfterCents"),
            description=d.get("description"),
        )


@dataclass
class TransactionPage:
    items: list[Transaction] = field(default_factory=list)
    next_cursor: str | None = None


@dataclass
class TrialInfo:
    #: The account can start a trial now.
    eligible: bool = False
    #: Trial length it would get, or got.
    days: int | None = None
    #: Trial credits, in cents.
    credit_cents: int | None = None
    #: Promo code held for the trial, if any.
    promo_code: str | None = None
    #: Trial end (ms); None when not trialing.
    ends_at: int | None = None
    #: Trial credits used (trialing only).
    used_cents: int | None = None
    remaining_cents: int | None = None

    @classmethod
    def _from_dict(cls, d: dict) -> "TrialInfo":
        return cls(
            eligible=bool(d.get("eligible")),
            days=d.get("days"),
            credit_cents=d.get("creditCents"),
            promo_code=d.get("promoCode"),
            ends_at=d.get("endsAt"),
            used_cents=d.get("usedCents"),
            remaining_cents=d.get("remainingCents"),
        )


@dataclass
class BillingPeriod:
    #: ``"trial"`` or ``"paid"``.
    kind: str
    start: int
    end: int
    #: 500 in the trial, 1900 in a paid month.
    included_cents: int
    used_cents: int
    #: Paid month: usage above the included credits.
    overage_cents: int = 0
    #: Of the overage, already invoiced.
    billed_overage_cents: int = 0
    unbilled_overage_cents: int = 0
    #: Paid month: unbilled overage at which the next invoice goes out.
    next_overage_charge_at_cents: int | None = None

    @classmethod
    def _from_dict(cls, d: dict) -> "BillingPeriod":
        return cls(
            kind=d.get("kind", ""),
            start=int(d.get("start") or 0),
            end=int(d.get("end") or 0),
            included_cents=int(d.get("includedCents") or 0),
            used_cents=int(d.get("usedCents") or 0),
            overage_cents=int(d.get("overageCents") or 0),
            billed_overage_cents=int(d.get("billedOverageCents") or 0),
            unbilled_overage_cents=int(d.get("unbilledOverageCents") or 0),
            next_overage_charge_at_cents=d.get("nextOverageChargeAtCents"),
        )


@dataclass
class Subscription:
    """The account's plan.

    ``plan``: ``"none"`` (no plan yet; creating anything raises
    :class:`~lizard.PaymentRequiredError`), ``"pro"``, ``"payg"`` (old prepaid credits,
    until 1 November 2026) or ``"enterprise"`` (pay as you go, invoiced monthly).
    ``status`` for Pro: ``"trialing"``, ``"active"``, ``"past_due"``, ``"canceled"``;
    ``"none"`` when there is no subscription.
    """

    plan: str
    status: str
    #: False when read for a workspace the caller does not own; card and invoice fields are then None.
    is_owner: bool = True
    #: 1900: $19/month, taxes included.
    price_cents: int = 1900
    tax_included: bool = True
    #: Credits included each paid month, in cents.
    included_cents: int = 1900
    trial: TrialInfo = field(default_factory=TrialInfo)
    #: The current Pro period; None when there is none.
    period: BillingPeriod | None = None
    #: ``{"at": ms, "amountCents": int}``; None when there is none, or the subscription is cancelling.
    next_charge: dict | None = None
    #: When a cancelled subscription ends (ms).
    cancel_at: int | None = None
    #: An invoice is unpaid.
    past_due: bool = False
    #: Stripe page that pays it (owner only).
    open_invoice_url: str | None = None
    #: ``{"brand", "last4", "expMonth", "expYear"}``.
    payment_method: dict | None = None
    #: Pro only: ``{"tier": "trial" | "pro", "replicasPerApp": int}``.
    limits: dict | None = None
    #: Pro Checkout is open for this account.
    checkout_available: bool = False

    @classmethod
    def _from_dict(cls, d: dict) -> "Subscription":
        return cls(
            plan=d.get("plan", ""),
            status=d.get("status", ""),
            is_owner=bool(d.get("isOwner", True)),
            price_cents=int(d.get("priceCents") or 1900),
            tax_included=bool(d.get("taxIncluded", True)),
            included_cents=int(d.get("includedCents") or 1900),
            trial=TrialInfo._from_dict(d.get("trial") or {}),
            period=BillingPeriod._from_dict(d["period"]) if d.get("period") else None,
            next_charge=d.get("nextCharge"),
            cancel_at=d.get("cancelAt"),
            past_due=bool(d.get("pastDue")),
            open_invoice_url=d.get("openInvoiceUrl"),
            payment_method=d.get("paymentMethod"),
            limits=d.get("limits"),
            checkout_available=bool(d.get("checkoutAvailable")),
        )


@dataclass
class CheckoutSession:
    #: Stripe Checkout page. The user finishes it in a browser.
    url: str
    session_id: str
    #: None when the account already had a trial: Pro starts at once and charges $19.
    trial_days: int | None = None
    trial_credit_cents: int | None = None

    @classmethod
    def _from_dict(cls, d: dict) -> "CheckoutSession":
        return cls(url=d.get("url", ""), session_id=d.get("sessionId", ""),
                   trial_days=d.get("trialDays"), trial_credit_cents=d.get("trialCreditCents"))


@dataclass
class StartProNowResult:
    """``status``: ``"active"`` (charged $19, the first paid month started),
    ``"requires_action"`` (the bank wants a confirmation, or declined: open
    ``invoice_url``; the trial continues) or ``"failed"`` (the trial continues)."""

    status: str
    invoice_url: str | None = None

    @classmethod
    def _from_dict(cls, d: dict) -> "StartProNowResult":
        return cls(status=d.get("status", ""), invoice_url=d.get("invoiceUrl"))


@dataclass
class PromoRedemption:
    #: ``"pending_payment_method"``: held for the trial Checkout starts. ``"applied"``: applied now.
    status: str
    #: The trial credits (older servers: the credit amount).
    credit_cents: int = 0
    code: str | None = None
    expires_at: int | None = None
    #: Kept for older clients.
    balance_cents: int = 0
    #: Trial length the code gives. None from servers before Pro.
    trial_days: int | None = None
    trial_credit_cents: int | None = None
    #: ``"next_checkout"``: held for the trial :meth:`BillingAPI.start_checkout` opens.
    #: ``"current_trial"``: extended the running trial.
    applies_to: str | None = None

    @classmethod
    def _from_dict(cls, d: dict) -> "PromoRedemption":
        return cls(
            status=d.get("status", ""),
            credit_cents=int(d.get("creditCents") or 0),
            code=d.get("code"),
            expires_at=d.get("expiresAt"),
            balance_cents=int(d.get("balanceCents") or 0),
            trial_days=d.get("trialDays"),
            trial_credit_cents=d.get("trialCreditCents"),
            applies_to=d.get("appliesTo"),
        )


class BillingAPI:
    """
    The account's plan, balance and usage.

    Pro costs $19/month, taxes included, with $19 of credits each month; usage above
    that is pay as you go, invoiced as it builds up. A new account starts with a
    7-day trial with $5 of credits. Enterprise is pay as you go, invoiced monthly. Old
    prepaid credits accounts (``plan == "payg"``) keep :meth:`balance` and
    :meth:`transactions` until 1 November 2026.

    Billing is **account-scoped, not workspace-scoped**: every workspace you create
    for a user bills to the account that owns the key. That is what makes per-user
    workspaces a safe pattern -- your users get isolation, you keep one bill.

    **Requires an unscoped key**, except :meth:`subscription` with a ``workspace_id``
    the key can reach. A scoped key is refused with 403 ``ACCOUNT_SCOPE_REQUIRED``,
    because a scoped key is meant to be handed to an end user, who should not be
    reading your card details or changing your plan. For per-workspace spend, use
    :class:`MetricsAPI`.

    Checkout and invoices are web pages: methods return their URL for the user to
    open. Nothing here retries a payment.
    """

    def __init__(self, client: "PlatformClient") -> None:
        self._client = client

    def subscription(self, *, workspace_id: str | None = None) -> Subscription:
        """The plan: trial, this month's credits, overage, next charge, cancel date.

        With ``workspace_id``, the plan of that workspace's owner (``is_owner`` False,
        no card or invoice fields).
        """
        from .client import query
        return Subscription._from_dict(self._client.get(query("/api/billing/subscription", workspaceId=workspace_id)))

    def start_checkout(self, *, return_url: str | None = None) -> CheckoutSession:
        """Open Stripe Checkout for Pro: the trial when the account can have one,
        otherwise Pro at once ($19 today). Returns the page for the user to finish;
        a second call while it is open returns the same session."""
        body = {"returnUrl": return_url} if return_url is not None else {}
        return CheckoutSession._from_dict(self._client.post("/api/billing/subscription/checkout", body))

    def start_pro_now(self) -> StartProNowResult:
        """End the trial now: charge $19 and start the first paid month with $19 of credits."""
        return StartProNowResult._from_dict(self._client.post("/api/billing/subscription/start-now", {}))

    def cancel(self) -> int | None:
        """Cancel Pro at the end of the current month or trial; returns when it ends (ms).

        Cancelling in the trial costs nothing.
        """
        return (self._client.post("/api/billing/subscription/cancel", {}) or {}).get("cancelAt")

    def resume(self) -> None:
        """Undo :meth:`cancel`: Pro renews as usual."""
        self._client.post("/api/billing/subscription/resume", {})

    def redeem_promo(self, code: str) -> PromoRedemption:
        """Redeem a promo code: a longer trial with more trial credits.

        Works only before the first payment.
        """
        return PromoRedemption._from_dict(self._client.post("/api/billing/promo/redeem", {"code": code}))

    def balance(self) -> Balance:
        """Prepaid credits balance, status, burn rate and runway (old ``payg`` accounts and enterprise)."""
        return Balance._from_dict(self._client.get("/api/billing/balance"))

    def transactions(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        include_usage: bool = False,
    ) -> TransactionPage:
        """A page of balance transactions, newest first (old ``payg`` accounts and enterprise)."""
        from .client import query
        body = self._client.get(query("/api/billing/transactions", limit=limit, cursor=cursor,
                                      includeUsage=1 if include_usage else None))
        return TransactionPage(
            items=[Transaction._from_dict(t) for t in (body.get("items") or [])],
            next_cursor=body.get("nextCursor"),
        )

    def summary(self) -> Any:
        """Cost summary for the current billing period, broken down by resource."""
        return self._client.get("/api/billing/summary")

    def live(self) -> Any:
        """Live (not-yet-invoiced) usage accumulating right now."""
        return self._client.get("/api/billing/live")

    def payment_methods(self):
        """Saved cards. Cards are added in Checkout or on the Billing page."""
        return self._client.get("/api/billing/payment-methods")

    def remove_payment_method(self, id: str):
        from .client import segment
        return self._client.delete(f"/api/billing/payment-methods/{segment(id)}")
