from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .client import PlatformClient


@dataclass
class MetricPoint:
    ts: int
    value: float

    @classmethod
    def _from_dict(cls, d: dict) -> "MetricPoint":
        return cls(ts=int(d.get("ts", 0)), value=float(d.get("value", 0)))


@dataclass
class ServiceMetrics:
    cpu: list[MetricPoint] = field(default_factory=list)
    memory: list[MetricPoint] = field(default_factory=list)
    network_rx: list[MetricPoint] = field(default_factory=list)
    network_tx: list[MetricPoint] = field(default_factory=list)
    disk_read: list[MetricPoint] = field(default_factory=list)
    disk_write: list[MetricPoint] = field(default_factory=list)


@dataclass
class CostMetrics:
    total_usd: float
    cpu_usd: float
    memory_usd: float
    storage_usd: float
    egress_usd: float


def _parse_points(raw: list | None) -> list[MetricPoint]:
    if not raw:
        return []
    return [MetricPoint._from_dict(p) if isinstance(p, dict) else MetricPoint(ts=0, value=float(p)) for p in raw]


class MetricsAPI:
    def __init__(self, client: "PlatformClient") -> None:
        self._client = client

    def cpu(self, service_id: str, *, since: str | None = None, until: str | None = None) -> list[MetricPoint]:
        """CPU usage over time (0–100% per vCPU)."""
        return _parse_points(self._client.get(self._qs(f"/api/apps/{service_id}/metrics/cpu", since, until)))

    def memory(self, service_id: str, *, since: str | None = None, until: str | None = None) -> list[MetricPoint]:
        """Memory usage over time (MiB)."""
        return _parse_points(self._client.get(self._qs(f"/api/apps/{service_id}/metrics/memory", since, until)))

    def network(self, service_id: str, *, since: str | None = None, until: str | None = None) -> dict:
        """Network I/O over time. Returns ``{"rx": [...], "tx": [...]}``."""
        result = self._client.get(self._qs(f"/api/apps/{service_id}/metrics/network", since, until))
        return {"rx": _parse_points(result.get("rx")), "tx": _parse_points(result.get("tx"))}

    def disk(self, service_id: str, *, since: str | None = None, until: str | None = None) -> dict:
        """Disk I/O over time. Returns ``{"read": [...], "write": [...]}``."""
        result = self._client.get(self._qs(f"/api/apps/{service_id}/metrics/disk", since, until))
        return {"read": _parse_points(result.get("read")), "write": _parse_points(result.get("write"))}

    def cost(self, project_id: str, *, since: str | None = None, until: str | None = None) -> CostMetrics:
        """Project cost breakdown."""
        result = self._client.get(self._qs(f"/api/projects/{project_id}/metrics/cost", since, until))
        return CostMetrics(
            total_usd=float(result.get("totalUsd", 0)),
            cpu_usd=float(result.get("cpuUsd", 0)),
            memory_usd=float(result.get("memoryUsd", 0)),
            storage_usd=float(result.get("storageUsd", 0)),
            egress_usd=float(result.get("egressUsd", 0)),
        )

    def all(self, service_id: str, *, since: str | None = None, until: str | None = None) -> ServiceMetrics:
        """All metrics for a service in one call."""
        return ServiceMetrics(
            cpu=self.cpu(service_id, since=since, until=until),
            memory=self.memory(service_id, since=since, until=until),
        )

    @staticmethod
    def _qs(path: str, since: str | None, until: str | None) -> str:
        params = []
        if since:
            params.append(f"since={since}")
        if until:
            params.append(f"until={until}")
        return f"{path}?{'&'.join(params)}" if params else path
