from __future__ import annotations
from dataclasses import dataclass
from .client import segment
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .client import PlatformClient


@dataclass
class DomainInfo:
    domain: str
    verified: bool
    cname_target: str | None = None
    service_id: str | None = None
    txt_record: str | None = None
    txt_value: str | None = None
    live: bool | None = None

    @classmethod
    def _from_dict(cls, d: dict) -> "DomainInfo":
        return cls(
            domain=d.get("hostname", d.get("domain", "")),
            txt_record=d.get("txtRecord"), txt_value=d.get("txtValue"), live=d.get("live"),
            verified=bool(d.get("verified", False)),
            cname_target=d.get("cnameTarget"),
            service_id=d.get("appId") or d.get("serviceId"),
        )


class DomainsAPI:
    def __init__(self, client: "PlatformClient") -> None:
        self._client = client

    def info(self, service_id: str) -> dict:
        return self._client.get(f"/api/apps/{service_id}/domains")

    def list(self, service_id: str) -> list[DomainInfo]:
        result = self.info(service_id)
        return [DomainInfo._from_dict({"domain": d, "verified": True, "cnameTarget": result.get("cnameTarget"), "live": result.get("dnsOk", {}).get(d)}) for d in result.get("domains", [])] + [DomainInfo._from_dict(d) for d in result.get("pending", [])]

    def add(self, service_id: str, domain: str, *, force: bool = False) -> DomainInfo:
        return DomainInfo._from_dict(self._client.post(f"/api/apps/{service_id}/domains", {"hostname": domain, "force": force}))

    def verify(self, service_id: str, domain: str) -> DomainInfo:
        return DomainInfo._from_dict(self._client.post(f"/api/apps/{service_id}/domains/verify", {"hostname": domain}))

    def generate(self, service_id: str) -> dict:
        return self._client.post(f"/api/apps/{service_id}/domains", {"generate": True})

    def delete(self, service_id: str, hostname: str) -> None:
        self._client.delete(f"/api/apps/{service_id}/domains/{segment(hostname)}")
