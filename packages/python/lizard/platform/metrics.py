from __future__ import annotations
from dataclasses import dataclass, field
from .client import query
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

    def service(self, id: str, *, range: str = "1h") -> dict:
        return self._client.get(query(f"/api/apps/{id}/metrics", range=range))

    def addon(self, project_id: str, addon_id: str, *, range: str = "1h") -> dict:
        return self._client.get(query(f"/api/projects/{project_id}/addons/{addon_id}/metrics", range=range))

    def project(self, id: str, *, range: str = "1h", live: bool = False) -> dict:
        return self._client.get(query(f"/api/projects/{id}/metrics", range=range, live=live))

    @staticmethod
    def _points(raw: dict, name: str) -> list[MetricPoint]:
        series = next((s for s in raw.get("series", []) if s["metric"] == name), {})
        available = series.get("available", [])
        return [MetricPoint(raw["timestamps"][i], value) for i, value in enumerate(series.get("values", [])) if i >= len(available) or available[i]]

    def cpu(self, id: str, *, range: str = "1h") -> list[MetricPoint]:
        return self._points(self.service(id, range=range), "cpu")

    def memory(self, id: str, *, range: str = "1h") -> list[MetricPoint]:
        return self._points(self.service(id, range=range), "memory")

    def network(self, id: str, *, range: str = "1h") -> dict:
        raw = self.service(id, range=range)
        return {"rx": self._points(raw, "network_rx"), "tx": self._points(raw, "network_tx")}

    def disk(self, id: str, *, range: str = "1h") -> dict:
        raw = self.service(id, range=range)
        return {"read": self._points(raw, "disk_read"), "write": self._points(raw, "disk_write")}

    def all(self, id: str, *, range: str = "1h") -> ServiceMetrics:
        raw = self.service(id, range=range)
        return ServiceMetrics(cpu=self._points(raw, "cpu"), memory=self._points(raw, "memory"),
            network_rx=self._points(raw, "network_rx"), network_tx=self._points(raw, "network_tx"),
            disk_read=self._points(raw, "disk_read"), disk_write=self._points(raw, "disk_write"))

    def cost(self, project_id: str, *, range: str = "30d") -> dict | None:
        project = self._client.get(f"/api/projects/{project_id}")
        summary = self._client.get(query("/api/billing/summary", workspaceId=project["workspaceId"], range=range))
        return next((p for p in summary["projects"] if p["projectId"] == project_id), None)
