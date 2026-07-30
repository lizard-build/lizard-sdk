from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .client import PlatformClient


@dataclass
class DomainInfo:
    domain: str
    verified: bool
    cname_target: str | None = None
    service_id: str | None = None

    @classmethod
    def _from_dict(cls, d: dict) -> "DomainInfo":
        return cls(
            domain=d.get("domain", ""),
            verified=bool(d.get("verified", False)),
            cname_target=d.get("cnameTarget"),
            service_id=d.get("appId") or d.get("serviceId"),
        )


class DomainsAPI:
    def __init__(self, client: "PlatformClient") -> None:
        self._client = client

    def list(self, service_id: str) -> list[DomainInfo]:
        """List all custom domains for a service."""
        result = self._client.get(f"/api/apps/{service_id}/domains")
        return [DomainInfo._from_dict(d) for d in (result if isinstance(result, list) else result.get("domains", []))]

    def add(self, service_id: str, domain: str) -> DomainInfo:
        """Add a custom domain to a service."""
        return DomainInfo._from_dict(self._client.post(f"/api/apps/{service_id}/domains", {"domain": domain}))

    def verify(self, service_id: str, domain: str) -> DomainInfo:
        """Check DNS verification status for a custom domain."""
        return DomainInfo._from_dict(
            self._client.post(f"/api/apps/{service_id}/domains/verify", {"domain": domain})
        )
