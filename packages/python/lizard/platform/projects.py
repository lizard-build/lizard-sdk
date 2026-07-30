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
        """Create a new project."""
        return Project._from_dict(self._client.post("/api/projects", {"workspaceId": workspace_id, "name": name}))

    def update(self, id: str, *, name: str | None = None) -> Project:
        """Rename a project."""
        return Project._from_dict(self._client.patch(f"/api/projects/{id}", {"name": name}))

    def delete(self, id: str) -> None:
        """Delete a project."""
        self._client.delete(f"/api/projects/{id}")
