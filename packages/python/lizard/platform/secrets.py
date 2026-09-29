from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .client import PlatformClient


@dataclass
class Secret:
    key: str
    value: str | None
    service_id: str | None = None
    project_id: str | None = None

    @classmethod
    def _from_dict(cls, d: dict) -> "Secret":
        return cls(
            key=d["key"],
            value=d.get("value"),
            service_id=d.get("serviceId") or d.get("appId"),
            project_id=d.get("projectId"),
        )


class SecretsAPI:
    def __init__(self, client: "PlatformClient") -> None:
        self._client = client

    def list(self, project_id: str, *, service_id: str | None = None) -> list[Secret]:
        path = f"/api/apps/{service_id}/secrets" if service_id else f"/api/projects/{project_id}/secrets"
        return [Secret._from_dict(s) for s in self._client.get(path)]

    def set(self, project_id: str, secrets: dict[str, str] | list[dict], *, service_id: str | None = None) -> None:
        items = [{"key": k, "value": v} for k, v in secrets.items()] if isinstance(secrets, dict) else secrets
        shared, services, names = {}, {}, {}
        for item in items:
            target = None if item.get("global") else item.get("serviceId", item.get("appId", service_id))
            if target:
                if target not in names:
                    svc = self._client.get(f"/api/apps/{target}")
                    if svc["projectId"] != project_id:
                        raise ValueError("Service does not belong to this project")
                    names[target] = svc["name"]
                services.setdefault(names[target], {})[item["key"]] = item["value"]
            else:
                shared[item["key"]] = item["value"]
        self._client.apply_config(project_id, {"secrets": {"shared": shared, "services": services}})

    def delete(self, project_id: str, key: str, *, service_id: str | None = None) -> None:
        self.set(project_id, [{"key": key, "value": None}], service_id=service_id)

    def refs(self, project_id: str, *, service_id: str | None = None):
        return self._client.get(f"/api/apps/{service_id}/variables:refs" if service_id else f"/api/projects/{project_id}/variables:refs")
