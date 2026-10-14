from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .client import PlatformClient


@dataclass
class Project:
    id: str
    name: str
    slug: str
    workspace_id: str

    @classmethod
    def _from_dict(cls, d: dict) -> "Project":
        return cls(id=d["id"], name=d["name"], slug=d.get("slug", ""), workspace_id=d.get("workspaceId", ""))


@dataclass
class PausedService:
    """One app or managed database a project / workspace pause or resume acted on."""
    kind: str  # "app" | "database" | "sandbox"
    id: str
    name: str
    reason: str | None = None  # set on skipped ones: why it was not paused / resumed

    @classmethod
    def _from_dict(cls, d: dict) -> "PausedService":
        return cls(kind=d.get("kind", ""), id=d["id"], name=d.get("name", ""), reason=d.get("reason"))


@dataclass
class PauseResult:
    """What projects.pause/resume and workspaces.pause/resume answer: what was done, and what
    was skipped with why (already paused, not running, busy, a storage bucket...)."""
    done: list[PausedService]
    skipped: list[PausedService]

    @classmethod
    def _from_dict(cls, d: dict | None) -> "PauseResult":
        d = d or {}
        return cls(
            done=[PausedService._from_dict(x) for x in d.get("done", [])],
            skipped=[PausedService._from_dict(x) for x in d.get("skipped", [])],
        )


class ProjectsAPI:
    def __init__(self, client: "PlatformClient") -> None:
        self._client = client

    def list(self, *, workspace_id: str | None = None) -> list[Project]:
        """List all projects the API key can access."""
        qs = f"?workspaceId={workspace_id}" if workspace_id else ""
        return [Project._from_dict(p) for p in self._client.get(f"/api/projects{qs}")]

    def get(self, id: str) -> Project:
        """Get a project by ID."""
        return Project._from_dict(self._client.get(f"/api/projects/{id}"))

    def create(self, *, workspace_id: str, name: str) -> Project:
        """Create a new project.

        A scoped key can create one only in a workspace it covers; anywhere else it
        gets HTTP 403 with ``code == "PROJECT_OUT_OF_SCOPE"``.
        """
        return Project._from_dict(self._client.post("/api/projects", {"workspaceId": workspace_id, "name": name}))

    def update(self, id: str, *, name: str | None = None) -> Project:
        """Rename a project."""
        return Project._from_dict(self._client.patch(f"/api/projects/{id}", {"name": name}))

    def pause(self, id: str) -> PauseResult:
        """Pause every app and managed database of a project: each scales to 0 and keeps its
        URL, host, port, password, settings and volumes. Skipped ones are listed with why."""
        return PauseResult._from_dict(self._client.post(f"/api/projects/{id}/pause"))

    def resume(self, id: str) -> PauseResult:
        """Resume what was paused in a project (not what a billing freeze paused)."""
        return PauseResult._from_dict(self._client.post(f"/api/projects/{id}/resume"))

    def delete(self, id: str) -> None:
        """Delete a project."""
        self._client.delete(f"/api/projects/{id}")

    def apply(self, id: str, config: dict) -> dict:
        """Apply config; pass revision to reject concurrent changes."""
        return self._client.apply_config(id, config)

    def services(self, id: str) -> dict:
        return self._client.get(f"/api/projects/{id}/services")

    def volume_limits(self, id: str) -> dict:
        return self._client.get(f"/api/projects/{id}/volume-limits")

    def logs(self, id: str, *, service: str | None = None, level: str | None = None, limit: int = 200, since: str | None = None, until: str | None = None):
        from .client import query
        return self._client.get(query(f"/api/projects/{id}/logs", service=service, level=level, limit=limit, since=since, until=until))

    def stream_logs(self, id: str):
        return self._client.events(f"/api/projects/{id}/logs/stream")
