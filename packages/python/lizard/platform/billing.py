from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .client import PlatformClient


@dataclass
class Balance:
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


class BillingAPI:
    """
    Account balance and usage.

    Billing is **account-scoped, not workspace-scoped**: every workspace you create
    for a user bills to the account that owns the key. That is what makes per-user
    workspaces a safe pattern -- your users get isolation, you keep one bill -- and
    also what makes :attr:`Balance.runway_hours` worth watching before you
    provision more.

    **Requires an unscoped key.** A scoped key is refused with 403
    ``ACCOUNT_SCOPE_REQUIRED``, because there is no workspace-scoped view of one
    shared balance, ledger and set of saved cards -- and because a scoped key is
    meant to be handed to an end user, who should not be reading your card details
    or spending against them. For per-workspace spend, use :class:`MetricsAPI`.
    """

    def __init__(self, client: "PlatformClient") -> None:
        self._client = client

    def balance(self) -> Balance:
        """Current balance, status, burn rate, and runway."""
        return Balance._from_dict(self._client.get("/api/billing/balance"))

    def transactions(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        include_usage: bool = False,
    ) -> TransactionPage:
        """A page of balance transactions, newest first."""
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
        return self._client.get("/api/billing/payment-methods")

    def setup_payment_method(self, return_url: str | None = None):
        return self._client.post("/api/billing/payment-methods/setup", {"returnUrl": return_url} if return_url else {})

    def remove_payment_method(self, id: str):
        from .client import segment
        return self._client.delete(f"/api/billing/payment-methods/{segment(id)}")

    def purchase(self, credit_cents: int, *, payment_method: str = "card", return_url: str | None = None):
        if type(credit_cents) is not int or credit_cents <= 0:
            raise ValueError("credit_cents must be a positive integer")
        if payment_method not in ("card", "crypto"):
            raise ValueError("payment_method must be card or crypto")
        body = {"creditCents": credit_cents, "paymentMethod": payment_method}
        if return_url is not None:
            body["returnUrl"] = return_url
        return self._client.post("/api/billing/purchase", body)

    def auto_topup(self):
        return self._client.get("/api/billing/auto-topup")

    def set_auto_topup(self, *, enabled: bool, threshold_cents: int, amount_cents: int, payment_method_ids: list[str]):
        return self._client.put("/api/billing/auto-topup", {"enabled": enabled, "thresholdCents": threshold_cents, "amountCents": amount_cents, "paymentMethodIds": payment_method_ids})

    def run_auto_topup(self):
        return self._client.post("/api/billing/auto-topup/run", {})

    def redeem_promo(self, code: str):
        return self._client.post("/api/billing/promo/redeem", {"code": code})

    def x402_quote(self, credit_cents: int):
        return self._client.post("/api/billing/purchase/x402/quote", {"creditCents": credit_cents})

    def payment_status(self, attempt_id: str):
        from .client import segment
        return self._client.get(f"/api/billing/purchase/x402/{segment(attempt_id)}")

    def pay_x402(self, credit_cents: int, *, max_total_cents: int, request_id: str | None = None, executable: str = "lizard"):
        """Pay using the CLI's durable x402 journal. Requires CLI >= 4.0.8."""
        from ..cli import LizardCLI
        if any(type(n) is not int or n <= 0 for n in (credit_cents, max_total_cents)):
            raise ValueError("Payment amounts must be positive integer cents")
        args = ["credits", "topup", f"{credit_cents // 100}.{credit_cents % 100:02}", "--method", "x402", "--max-total", f"{max_total_cents // 100}.{max_total_cents % 100:02}", "--yes"]
        if request_id:
            args += ["--request-id", request_id]
        config = self._client._config
        result = LizardCLI(api_key=config.api_key, api_url=config.api_url, executable=executable).run(args)
        if result.code:
            raise RuntimeError(f"x402 CLI exited with code {result.code}; inspect the payment journal or query payment_status before retrying")
        return result.events[0] if result.events else None
