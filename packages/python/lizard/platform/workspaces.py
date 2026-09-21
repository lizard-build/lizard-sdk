from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .client import PlatformClient


@dataclass
class Workspace:
    id: str
    name: str
    slug: str
    #: ``owner`` | ``admin`` | ``member`` -- the calling account's role here.
    role: str | None = None
    #: True for the account's own workspace, which cannot be deleted.
    is_personal: bool = False
    project_count: int = 0
    plan: str | None = None

    @classmethod
    def _from_dict(cls, d: dict) -> "Workspace":
        return cls(
            id=d["id"],
            name=d.get("name", ""),
            slug=d.get("slug", ""),
            role=d.get("role"),
            is_personal=bool(d.get("isPersonal", False)),
            project_count=int(d.get("projectCount") or 0),
            plan=d.get("plan"),
        )


class WorkspacesAPI:
    """
    Workspaces -- the top of the ownership tree: a workspace holds projects, a
    project holds services, sandboxes and volumes.

    This is the missing first step of per-user provisioning. Handing each of your
    users their own workspace, plus an API key scoped to it, is what keeps them
    isolated from one another while all of it bills to your account::

        ws = lizard.workspaces.create(name=f"user-{user_id}")
        prj = lizard.projects.create(workspace_id=ws.id, name="default")
        key = lizard.api_keys.create(name=f"user-{user_id}", workspaces=[ws.id])
        # hand key.key to that user -- it reaches nothing outside ws

    See :class:`ApiKeysAPI` for the scoping half of that flow.
    """

    def __init__(self, client: "PlatformClient") -> None:
        self._client = client

    def list(self) -> list[Workspace]:
        """List workspaces the calling credential can see.

        A scoped API key sees only what it is scoped to: a workspace-scoped key
        returns that one workspace, and a project-scoped key returns the workspace
        containing its project. A full key returns every workspace the account
        belongs to.
        """
        return [Workspace._from_dict(w) for w in self._client.get("/api/workspaces")]

    def create(self, *, name: str) -> Workspace:
        """Create a workspace. The caller becomes its owner."""
        return Workspace._from_dict(self._client.post("/api/workspaces", {"name": name}))

    def delete(self, id: str, *, force: bool = False) -> None:
        """Delete a workspace.

        Empty-only by default -- the server refuses while any project, sandbox or
        volume remains, so this cannot quietly destroy a user's work. ``force=True``
        deletes the workspace and everything in it, irreversibly.
        """
        qs = "" if force else "?requireEmpty=true"
        self._client.delete(f"/api/workspaces/{id}{qs}")

    def find(self, name_or_slug_or_id: str) -> Workspace | None:
        """Find a workspace by name, slug, or id, or ``None``.

        Matching is exact; id wins, then slug, then name.
        """
        all_ws = self.list()
        for key in ("id", "slug", "name"):
            for w in all_ws:
                if getattr(w, key) == name_or_slug_or_id:
                    return w
        return None
