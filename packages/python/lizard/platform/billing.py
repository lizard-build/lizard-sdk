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
        params = []
        if limit is not None:
            params.append(f"limit={limit}")
        if cursor:
            params.append(f"cursor={cursor}")
        if include_usage:
            params.append("includeUsage=1")
        qs = f"?{'&'.join(params)}" if params else ""
        body = self._client.get(f"/api/billing/transactions{qs}")
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
