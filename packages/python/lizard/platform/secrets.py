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
        """List secrets for a project (optionally filtered to a service)."""
        qs = f"?appId={service_id}" if service_id else ""
        result = self._client.get(f"/api/projects/{project_id}/secrets{qs}")
        return [Secret._from_dict(s) for s in (result if isinstance(result, list) else result.get("secrets", []))]

    def set(
        self,
        project_id: str,
        secrets: dict[str, str] | list[dict],
        *,
        service_id: str | None = None,
    ) -> None:
        """
        Set one or more secrets. Accepts a plain dict or a list of
        ``{"key": "K", "value": "V", "serviceId": "..."}`` objects.
        """
        if isinstance(secrets, dict):
            items = [{"key": k, "value": v, **({"appId": service_id} if service_id else {})}
                     for k, v in secrets.items()]
        else:
            items = [
                {**s, **({"appId": service_id} if service_id and "serviceId" not in s else {})}
                for s in secrets
            ]
        self._client.post(f"/api/projects/{project_id}/secrets", {"secrets": items})

    def delete(self, project_id: str, key: str, *, service_id: str | None = None) -> None:
        """Delete a secret by key."""
        body: dict = {"key": key}
        if service_id:
            body["appId"] = service_id
        self._client.delete(f"/api/projects/{project_id}/secrets", body)
