from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .client import PlatformClient
    from .projects import PauseResult


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


@dataclass
class ResalePricing:
    """Resale prices: each resource's price as a multiple of Lizard's (1-100). API keys
    scoped to the workspace see prices and costs multiplied by these; the owner's bill
    does not change."""
    #: False when every multiplier is 1: scoped keys see Lizard's prices.
    enabled: bool
    cpu: float = 1
    memory: float = 1
    #: Volumes.
    storage: float = 1
    egress: float = 1
    object_storage: float = 1
    #: Sized sandboxes' flat price.
    sandbox: float = 1

    @classmethod
    def _from_dict(cls, d: dict) -> "ResalePricing":
        m = d.get("multipliers") or {}
        return cls(
            enabled=bool(d.get("enabled", False)),
            cpu=m.get("cpu", 1),
            memory=m.get("memory", 1),
            storage=m.get("storage", 1),
            egress=m.get("egress", 1),
            object_storage=m.get("objectStorage", 1),
            sandbox=m.get("sandbox", 1),
        )


@dataclass
class WorkspaceLimits:
    """What a workspace may run at once; ``None``: no limit."""
    #: Sandboxes running (or resuming) at once; paused ones do not count.
    max_running_sandboxes: int | None = None
    #: vCPU its apps and databases may be using right now (measured).
    max_cpu_vcpus: float | None = None
    #: Memory (MB) its apps and databases may be using right now (measured).
    max_memory_mb: int | None = None
    #: Sandboxes running now.
    running_sandboxes: int = 0
    #: Measured use of its apps and databases, all regions.
    cpu_vcpus: float = 0.0
    memory_mb: float = 0.0
    #: Unix ms of the oldest reading in the sum; None when nothing was measured.
    measured_at: int | None = None

    @classmethod
    def _from_dict(cls, d: dict) -> "WorkspaceLimits":
        lim, use = d.get("limits") or {}, d.get("usage") or {}
        return cls(
            max_running_sandboxes=lim.get("maxRunningSandboxes"),
            max_cpu_vcpus=lim.get("maxCpuVcpus"),
            max_memory_mb=lim.get("maxMemoryMb"),
            running_sandboxes=int(use.get("runningSandboxes") or 0),
            cpu_vcpus=float(use.get("cpuVcpus") or 0),
            memory_mb=float(use.get("memoryMb") or 0),
            measured_at=use.get("measuredAt"),
        )


_UNCHANGED = object()


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
        """Create a workspace. The caller becomes its owner.

        Needs a key with no scopes: a scoped key gets HTTP 403 with
        ``code == "ACCOUNT_SCOPE_REQUIRED"``.
        """
        return Workspace._from_dict(self._client.post("/api/workspaces", {"name": name}))

    def pause(self, id: str) -> "PauseResult":
        """Pause every app and managed database in every project of a workspace (owner only).
        Each keeps its URL, host, port, password, settings and volumes."""
        from .projects import PauseResult
        return PauseResult._from_dict(self._client.post(f"/api/workspaces/{id}/pause"))

    def resume(self, id: str) -> "PauseResult":
        """Resume what was paused in a workspace (owner only; not what a billing freeze paused)."""
        from .projects import PauseResult
        return PauseResult._from_dict(self._client.post(f"/api/workspaces/{id}/resume"))

    def get_resale_pricing(self, id: str) -> ResalePricing:
        """The workspace's resale prices (owner only, key with no scopes). A scoped key
        gets HTTP 403 ``ACCOUNT_SCOPE_REQUIRED``: the keys that see these prices can
        neither read nor change them."""
        return ResalePricing._from_dict(self._client.get(f"/api/workspaces/{id}/resale-pricing"))

    def set_resale_pricing(
        self,
        id: str,
        *,
        cpu: float | None = None,
        memory: float | None = None,
        storage: float | None = None,
        egress: float | None = None,
        object_storage: float | None = None,
        sandbox: float | None = None,
    ) -> ResalePricing:
        """Set the workspace's resale prices (owner only, key with no scopes). Replaces
        them all: a resource left out is 1. Every API key scoped to the workspace, or to
        one of its projects, then sees each price and cost multiplied (sandbox
        prices, ``metrics`` costs, billing summaries). Display only: what
        Lizard bills you is unchanged.

        ``lizard.workspaces.set_resale_pricing(ws.id, cpu=4, memory=4, sandbox=4)``
        """
        body = {k: v for k, v in {
            "cpu": cpu, "memory": memory, "storage": storage, "egress": egress,
            "objectStorage": object_storage, "sandbox": sandbox,
        }.items() if v is not None}
        return ResalePricing._from_dict(self._client.put(f"/api/workspaces/{id}/resale-pricing", body))

    def clear_resale_pricing(self, id: str) -> ResalePricing:
        """Turn resale prices off: scoped keys see Lizard's prices again (owner only)."""
        return ResalePricing._from_dict(self._client.put(f"/api/workspaces/{id}/resale-pricing", {}))

    def get_limits(self, id: str) -> WorkspaceLimits:
        """The workspace's limits and what it uses now. Anyone in the workspace may read
        them, including a key scoped to it."""
        return WorkspaceLimits._from_dict(self._client.get(f"/api/workspaces/{id}/limits"))

    def set_limits(
        self,
        id: str,
        *,
        max_running_sandboxes: "int | None | object" = _UNCHANGED,
        max_cpu_vcpus: "float | None | object" = _UNCHANGED,
        max_memory_mb: "int | None | object" = _UNCHANGED,
    ) -> WorkspaceLimits:
        """Limit what a workspace may run at once (owner only, key with no scopes). A
        limit you do not pass stays as it is; ``None`` removes it.

        ``max_running_sandboxes``: a create, fork or resume past it fails with HTTP 429
        ``WORKSPACE_SANDBOX_LIMIT``. ``max_cpu_vcpus`` / ``max_memory_mb``: what its apps and
        databases *use* (measured every ~10 s); while at or over a cap, deploys, restarts,
        scale-ups, new databases and resumes there fail with HTTP 429
        ``WORKSPACE_USAGE_LIMIT``; services already running keep running.

        ``lizard.workspaces.set_limits(ws.id, max_running_sandboxes=5, max_cpu_vcpus=2, max_memory_mb=4096)``
        """
        body = {k: v for k, v in {
            "maxRunningSandboxes": max_running_sandboxes, "maxCpuVcpus": max_cpu_vcpus, "maxMemoryMb": max_memory_mb,
        }.items() if v is not _UNCHANGED}
        return WorkspaceLimits._from_dict(self._client.put(f"/api/workspaces/{id}/limits", body))

    def delete(self, id: str, *, force: bool = False) -> None:
        """Delete a workspace.

        Empty-only by default -- the server refuses while any project, sandbox or
        volume remains, so this cannot quietly destroy a user's work. ``force=True``
        deletes the workspace with its apps, addons and projects, irreversibly. It
        does not delete sandboxes, sandbox volumes or snapshots: a running sandbox
        keeps running with no workspace left to find it in. Kill the workspace's
        sandboxes and delete its volumes and snapshots first.
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
