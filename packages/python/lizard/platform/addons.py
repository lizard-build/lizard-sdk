from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from .client import PlatformClient

AddonType = Literal["postgres", "mysql", "mongodb", "mongo", "redis", "s3"]


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
        for addon in self.list(project_id=project_id):
            if addon.id == addon_id:
                return addon
        from ..errors import NotFoundError
        raise NotFoundError("Addon not found")

    def create(
        self,
        *,
        project_id: str,
        name: str | None = None,
        type: AddonType,
        version: str | None = None,
        storage_mi: int | None = None,
        memory_mi: int | None = None,
        cpu_millis: int | None = None,
        region: str | None = None,
    ) -> Addon:
        """Create an addon (database, cache, or object storage)."""
        config = {k: v for k, v in {"version": version,
            "storageSize": f"{storage_mi}Mi" if storage_mi is not None else None,
            "memoryLimit": f"{memory_mi}Mi" if memory_mi is not None else None,
            "cpuLimit": f"{cpu_millis}m" if cpu_millis is not None else None}.items() if v is not None}
        body = {"type": "mongo" if type == "mongodb" else type, "config": config}
        if name is not None: body["name"] = name
        if region is not None: body["region"] = region
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
        limits = {}
        if cpu_millis is not None:
            if cpu_millis % 1000:
                raise ValueError("Addon CPU must be a whole number of vCPUs")
            limits["vcpu"] = cpu_millis // 1000
        if memory_mi is not None: limits["memoryMb"] = memory_mi
        addon = {"id": addon_id, "limits": limits}
        if storage_mi is not None: addon["storageSize"] = f"{storage_mi}Mi"
        self._client.apply_config(project_id, {"addons": [addon]})
        return self.get(project_id, addon_id)

    def redeploy(self, project_id: str, addon_id: str) -> None:
        """Trigger a redeploy of an addon."""
        self._client.post(f"/api/projects/{project_id}/addons/{addon_id}/redeploy")

    def rename(self, project_id: str, addon_id: str, name: str):
        return self._client.patch(f"/api/projects/{project_id}/addons/{addon_id}", {"name": name})

    def secrets(self, project_id: str, addon_id: str):
        return self._client.get(f"/api/projects/{project_id}/addons/{addon_id}/secrets")

    def logs(self, project_id: str, addon_id: str):
        return self._client.get(f"/api/projects/{project_id}/addons/{addon_id}/logs")
