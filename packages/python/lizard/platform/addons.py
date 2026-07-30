from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from .client import PlatformClient

AddonType = Literal["postgres", "mysql", "mongodb", "redis", "s3"]


@dataclass
class Addon:
    id: str
    name: str
    type: str
    project_id: str
    status: str
    region: str | None = None
    version: str | None = None
    storage_mi: int | None = None
    memory_mi: int | None = None
    cpu_millis: int | None = None

    @classmethod
    def _from_dict(cls, d: dict) -> "Addon":
        return cls(
            id=d["id"],
            name=d["name"],
            type=d.get("type", ""),
            project_id=d.get("projectId", ""),
            status=d.get("status", "none"),
            region=d.get("region"),
            version=d.get("version"),
            storage_mi=d.get("storageMi"),
            memory_mi=d.get("memoryMi"),
            cpu_millis=d.get("cpuMillis"),
        )


class AddonsAPI:
    def __init__(self, client: "PlatformClient") -> None:
        self._client = client

    def list(self, *, project_id: str) -> list[Addon]:
        """List all addons in a project."""
        return [Addon._from_dict(a) for a in self._client.get(f"/api/projects/{project_id}/addons")]

    def get(self, project_id: str, addon_id: str) -> Addon:
        """Get an addon by project + addon ID."""
        return Addon._from_dict(self._client.get(f"/api/projects/{project_id}/addons/{addon_id}"))

    def create(
        self,
        *,
        project_id: str,
        name: str,
        type: AddonType,
        version: str | None = None,
        storage_mi: int | None = None,
        memory_mi: int | None = None,
        cpu_millis: int | None = None,
        region: str | None = None,
    ) -> Addon:
        """Create an addon (database, cache, or object storage)."""
        body = {k: v for k, v in {
            "name": name,
            "type": type,
            "version": version,
            "storageMi": storage_mi,
            "memoryMi": memory_mi,
            "cpuMillis": cpu_millis,
            "region": region,
        }.items() if v is not None}
        return Addon._from_dict(self._client.post(f"/api/projects/{project_id}/addons", body))

    def delete(self, project_id: str, addon_id: str) -> None:
        """Delete an addon."""
        self._client.delete(f"/api/projects/{project_id}/addons/{addon_id}")

    def resize(
        self,
        project_id: str,
        addon_id: str,
        *,
        storage_mi: int | None = None,
        memory_mi: int | None = None,
        cpu_millis: int | None = None,
    ) -> Addon:
        """Resize an addon's resources."""
        body = {k: v for k, v in {
            "storageMi": storage_mi,
            "memoryMi": memory_mi,
            "cpuMillis": cpu_millis,
        }.items() if v is not None}
        return Addon._from_dict(self._client.patch(f"/api/projects/{project_id}/addons/{addon_id}", body))

    def redeploy(self, project_id: str, addon_id: str) -> None:
        """Trigger a redeploy of an addon."""
        self._client.post(f"/api/projects/{project_id}/addons/{addon_id}/redeploy")
