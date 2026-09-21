from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from .client import PlatformClient

ScopeType = Literal["workspace", "project"]


@dataclass
class ApiKeyScope:
    type: ScopeType
    id: str
    #: Present on read; the server resolves the scoped resource's name.
    name: str | None = None


@dataclass
class ApiKey:
    id: str
    name: str
    #: A masked fragment. The full key is only ever returned once, on create.
    key_preview: str | None = None
    scopes: list[ApiKeyScope] = field(default_factory=list)
    created_at: int | None = None
    last_used_at: int | None = None
    #: The full ``liz_`` secret. Populated **only** on :meth:`ApiKeysAPI.create`.
    key: str | None = None

    @classmethod
    def _from_dict(cls, d: dict) -> "ApiKey":
        return cls(
            id=d["id"],
            name=d.get("name", ""),
            key_preview=d.get("keyPreview"),
            scopes=[
                ApiKeyScope(type=s["type"], id=s["id"], name=s.get("name"))
                for s in (d.get("scopes") or [])
            ],
            created_at=d.get("createdAt"),
            last_used_at=d.get("lastUsedAt"),
            key=d.get("key"),
        )


class ApiKeysAPI:
    """
    API keys, including the scoped keys that make per-user isolation possible.

    **A key with no scope has full access** to every workspace and project the
    creating account can reach. Pass ``workspaces`` or ``projects`` to bound it.
    Scopes are enforced server-side on every route, so a scoped key that leaks --
    out of a sandbox, a log, a user's machine -- reaches only what it was scoped to.

    A scoped key cannot mint a broader key: that check is server-side and exact, so
    handing a user a workspace-scoped key is not a step away from full access.

    Give each of your users their own isolated workspace::

        ws = lizard.workspaces.create(name=f"user-{user_id}")
        prj = lizard.projects.create(workspace_id=ws.id, name="default")
        key = lizard.api_keys.create(name=f"user-{user_id}", workspaces=[ws.id])
        # key.key is visible only here. Store it now.

    Let a sandbox use the CLI as that user, and nothing more::

        sandbox = Sandbox.create(
            "codex",
            project_id=prj.id,
            lizard_token=key.key,  # scoped -- safe to expose to code in the sandbox
        )
        sandbox.process.exec_("lizard volume list")
    """

    def __init__(self, client: "PlatformClient") -> None:
        self._client = client

    def list(self) -> list[ApiKey]:
        """List the account's API keys. Previews only -- no full keys."""
        return [ApiKey._from_dict(k) for k in self._client.get("/api/account/api-keys")]

    def create(
        self,
        *,
        name: str,
        workspaces: list[str] | None = None,
        projects: list[str] | None = None,
        scopes: list[ApiKeyScope] | None = None,
    ) -> ApiKey:
        """Create an API key.

        The returned :attr:`ApiKey.key` is the only place the full secret appears --
        it is stored hashed and no later request can read it back.

        Omitting every scope creates a full-access key; the server rejects an attempt
        to create one from a key that is itself scoped.
        """
        all_scopes: list[dict] = [{"type": s.type, "id": s.id} for s in (scopes or [])]
        all_scopes += [{"type": "workspace", "id": i} for i in (workspaces or [])]
        all_scopes += [{"type": "project", "id": i} for i in (projects or [])]
        return ApiKey._from_dict(
            self._client.post("/api/account/api-keys", {"name": name, "scopes": all_scopes})
        )

    def delete(self, id: str) -> None:
        """Revoke a key by id. It stops working immediately, everywhere."""
        self._client.delete(f"/api/account/api-keys/{id}")
