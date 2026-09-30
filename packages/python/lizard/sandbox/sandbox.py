from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Literal, TypedDict
import time

from ..config import ConnectionConfig, HTTP_TIMEOUT_S, DEFAULT_SANDBOX_TIMEOUT_MS
from .process import Process
from .fs import Fs


class SandboxSnapshot(TypedDict):
    id: str
    name: str
    projectId: str
    workspaceId: str
    region: str
    sourceSandboxId: str
    status: Literal["building", "warming", "ready", "paused", "suspended", "failed"]
    poolSize: int
    readyCount: int
    error: str | None
    cpus: int
    memoryMb: int
    createdAt: int


@dataclass
class SandboxInfo:
    sandbox_id: str
    template: str
    started_at: str
    end_at: str
    #: Region the sandbox runs in -- the volume's region when one is attached.
    region: str | None = None
    status: str | None = None
    pause_error: str | None = None
    size: str | None = None
    price_per_hour: float | None = None
    cpus: int | None = None
    memory_mb: int | None = None
    metadata: dict[str, str] | None = None


def _to_sandbox_info(s: dict) -> SandboxInfo:
    """Build a SandboxInfo from either sandbox response shape.

    Every field but the id is read with .get(): a sandbox read back immediately
    after its create is answered from the in-flight record, which carries fewer
    fields than the stored row, and requiring startedAt there made get_info()
    raise KeyError on a sandbox that was running perfectly well.
    """
    return SandboxInfo(
        sandbox_id=s.get("sandboxId") or s["id"],
        template=s.get("template", ""),
        started_at=s.get("startedAt", ""),
        end_at=s.get("endAt") or s.get("expiresAt") or "",
        region=s.get("region"),
        status=s.get("status"),
        pause_error=s.get("pauseError"),
        size=s.get("size"),
        price_per_hour=s.get("pricePerHour"),
        cpus=s.get("cpus"),
        memory_mb=s.get("memoryMb"),
        metadata=s.get("metadata"),
    )


class Sandbox:
    """
    A Linux sandbox running on Kubernetes.

    Run commands, read and write files, and expose HTTP ports in a sandbox.

    Sandboxes are **ephemeral**: killing one, or letting it hit its timeout,
    discards everything written inside it. State that has to outlive a sandbox
    belongs on a :class:`~lizard.Volume`, a separate disk mounted at ``/workspace``
    that a later sandbox can re-attach.

    Example::

        from lizard import Sandbox

        with Sandbox.create("base", project="my-project") as sandbox:
            sandbox.fs.write("/tmp/hello.txt", "hello world")
            result = sandbox.process.exec_("cat /tmp/hello.txt")
            if result.exit_code != 0:
                raise RuntimeError(result.stderr)
            print(result.stdout)

    Can also be used as a context manager::

        with Sandbox.create("interpreter", project="my-project") as sandbox:
            sandbox.fs.write("/app/main.py", "print('done')")
            sandbox.process.exec_("python /app/main.py")
    """

    _default_template = "base"
    _default_timeout_ms = DEFAULT_SANDBOX_TIMEOUT_MS

    def __init__(
        self,
        sandbox_id: str,
        *,
        api_key: str | None = None,
        api_url: str | None = None,
        timeout_ms: int | None = None,
    ):
        self.sandbox_id = sandbox_id
        self._config = ConnectionConfig(api_key=api_key, api_url=api_url, timeout_ms=timeout_ms)
        self.fs = Fs(self.sandbox_id, self._config)
        self.process = Process(self.sandbox_id, self._config)

    @classmethod
    def create(
        cls,
        template: str | None = None,
        *,
        snapshot_id: str | None = None,
        size: Literal["small", "medium", "large"] | None = None,
        project: str | None = None,
        project_id: str | None = None,
        api_key: str | None = None,
        api_url: str | None = None,
        timeout_ms: int | None = None,
        metadata: dict[str, str] | None = None,
        envs: dict[str, str] | None = None,
        region: str | None = None,
        volume_id: str | None = None,
        volume_name: str | None = None,
        lizard_token: str | None = None,
    ) -> "Sandbox":
        """
        Boot a new Lizard sandbox from the specified template.

        Template availability and installed tools depend on the platform and region.
        Use ``base`` for shell commands or ``interpreter`` for Python process commands.
        Hosted templates do not support the legacy ``CodeSandbox`` execution API.

        Every sandbox must belong to a project — billing is metered per project.
        Pass ``project`` (its ID, slug, or name) or an exact ``project_id``, or
        create sandboxes through a :class:`~lizard.Lizard` client, which pins the
        project for you.

        :param template: Template name. Defaults to ``base``.
        :param project: Project ID, slug, or name the sandbox belongs to.
        :param project_id: Exact project ID — skips resolving ``project``.
        :param region: Region to run the sandbox in, e.g. ``"us-east-1"``. Leave
            unset when attaching a volume: a volume is node-local, so the server
            places the sandbox in the volume's own region. Naming a region the
            volume is not in is rejected with a 400 rather than silently moved —
            that combination cannot be satisfied. Defaults to the platform's
            default sandbox region.
        :param volume_name: Attach a persistent volume by name, mounted at
            ``/workspace``. A volume's name is its key inside a project, so this is
            usually what you want. Requires an exact ``project_id``.
        :param volume_id: Attach a persistent volume by id, mounted at ``/workspace``
            inside the sandbox. See :class:`lizard.Volume`.
        :param lizard_token: A ``liz_`` API key to write into the sandbox so the
            ``lizard`` CLI works inside it. The CLI is preinstalled in every
            template; this is what authenticates it. The key must belong to the
            caller — the server verifies that and skips the injection otherwise.

            **Security:** anything running in the sandbox can read this key, and
            sandboxes run untrusted code. Pass a **workspace-scoped** key rather
            than a full-access one. Scopes are enforced end to end, so a scoped
            key that escapes is bounded to that one workspace.

        Example::

            sandbox = Sandbox.create("base", project="my-project")
        """
        import httpx

        from ..project import require_project_ref, resolve_project_id

        # A sandbox must belong to a project — billing is metered per project.
        # The API rejects project-less creates with 400 PROJECT_REQUIRED;
        # checking here first reports the missing project before the missing key.
        exact_id, project_ref = require_project_ref(project=project, project_id=project_id)
        config = ConnectionConfig(api_key=api_key, api_url=api_url, timeout_ms=timeout_ms)
        effective_template = template or cls._default_template
        effective_timeout = timeout_ms if timeout_ms is not None else cls._default_timeout_ms
        resolved_project_id = exact_id or resolve_project_id(project_ref, config)

        body: dict[str, Any] = {
            "template": effective_template,
            "timeoutMs": effective_timeout,
            "projectId": resolved_project_id,
        }
        if snapshot_id is not None:
            body["snapshotId"] = snapshot_id
        if size is not None:
            body["size"] = size
        if metadata:
            body["metadata"] = metadata
        if envs:
            body["envs"] = envs
        if region:
            body["region"] = region
        if volume_id:
            body["volumeId"] = volume_id
        if volume_name:
            body["volumeName"] = volume_name
        if lizard_token:
            body["lizardToken"] = lizard_token

        res = httpx.post(
            f"{config.api_url}/api/sandboxes",
            headers=config.headers,
            json=body,
            timeout=HTTP_TIMEOUT_S,
        )

        if not res.is_success:
            from ..errors import handle_api_error
            handle_api_error(res.status_code, res.text)

        data = res.json()
        return cls(
            data["sandboxId"],
            api_key=api_key,
            api_url=api_url,
            timeout_ms=timeout_ms,
        )

    @classmethod
    def connect(
        cls,
        sandbox_id: str,
        *,
        api_key: str | None = None,
        api_url: str | None = None,
    ) -> "Sandbox":
        """
        Connect to an existing sandbox by its ID.

        Verifies the sandbox exists and is reachable, then returns a handle to it.
        Raises :class:`~lizard.NotFoundError` if it has been killed or expired.

        Connecting reads sandbox metadata without changing its state.

        Example::

            sandbox = Sandbox.connect("sandbox_abc123")
        """
        import httpx

        config = ConnectionConfig(api_key=api_key, api_url=api_url)
        res = httpx.get(
            f"{config.api_url}/api/sandboxes/{sandbox_id}",
            headers=config.headers,
            timeout=HTTP_TIMEOUT_S,
        )
        if not res.is_success:
            from ..errors import handle_api_error
            handle_api_error(res.status_code, res.text)

        return cls(sandbox_id, api_key=api_key, api_url=api_url)

    @classmethod
    def list(cls, *, project_id: str | None = None, api_key: str | None = None, api_url: str | None = None) -> list[SandboxInfo]:
        """List all running sandboxes for the authenticated account."""
        import httpx

        config = ConnectionConfig(api_key=api_key, api_url=api_url)
        res = httpx.get(f"{config.api_url}/api/projects/{project_id}/sandboxes" if project_id else f"{config.api_url}/api/sandboxes", headers=config.headers, timeout=HTTP_TIMEOUT_S)
        if not res.is_success:
            from ..errors import handle_api_error
            handle_api_error(res.status_code, res.text)

        return [
            _to_sandbox_info(s)
            for s in res.json()
        ]

    def kill(self) -> bool:
        """
        Kill the sandbox and release its resources immediately.

        :returns: ``True`` if the sandbox was terminated, ``False`` if it was already gone.
        """
        import httpx

        res = httpx.delete(
            f"{self._config.api_url}/api/sandboxes/{self.sandbox_id}",
            headers=self._config.headers,
            timeout=HTTP_TIMEOUT_S,
        )
        if res.status_code == 404:
            return False
        if not res.is_success:
            from ..errors import handle_api_error
            handle_api_error(res.status_code, res.text)
        return True

    def pause(self) -> bool:
        """Queue CRIU capture. Wait for status 'paused' before resuming."""
        import httpx

        res = httpx.post(
            f"{self._config.api_url}/api/sandboxes/{self.sandbox_id}/pause",
            headers=self._config.headers,
            timeout=HTTP_TIMEOUT_S,
        )
        if res.status_code == 404:
            return False
        if not res.is_success:
            from ..errors import handle_api_error
            handle_api_error(res.status_code, res.text)
        return True

    def resume(self) -> bool:
        """Queue restoration. Wait for status 'running' before executing commands."""
        import httpx

        res = httpx.post(
            f"{self._config.api_url}/api/sandboxes/{self.sandbox_id}/resume",
            headers=self._config.headers,
            timeout=HTTP_TIMEOUT_S,
        )
        if res.status_code == 404:
            return False
        if not res.is_success:
            from ..errors import handle_api_error
            handle_api_error(res.status_code, res.text)
        return True

    def set_timeout(self, timeout_ms: int) -> None:
        """Extend or reduce the sandbox timeout."""
        import httpx

        res = httpx.post(
            f"{self._config.api_url}/api/sandboxes/{self.sandbox_id}/timeout",
            headers=self._config.headers,
            json={"timeoutMs": timeout_ms},
            timeout=HTTP_TIMEOUT_S,
        )
        if not res.is_success:
            from ..errors import handle_api_error
            handle_api_error(res.status_code, res.text)

    def get_info(self) -> SandboxInfo:
        """Get metadata and status information about this sandbox."""
        import httpx

        res = httpx.get(
            f"{self._config.api_url}/api/sandboxes/{self.sandbox_id}",
            headers=self._config.headers,
            timeout=HTTP_TIMEOUT_S,
        )
        if not res.is_success:
            from ..errors import handle_api_error
            handle_api_error(res.status_code, res.text)

        return _to_sandbox_info(res.json())

    def get_host(self, port: int) -> str:
        """
        Register a public HTTPS route for a port inside the sandbox and return
        the hostname (without scheme).

        :param port: Port number the service is listening on inside the sandbox.

        Example::

            # Start an HTTP server on port 3000 before exposing it.
            hostname = sandbox.get_host(3000)
            print(f"https://{hostname}")
        """
        import httpx
        res = httpx.post(
            f"{self._config.api_url}/api/sandboxes/{self.sandbox_id}/expose/{port}",
            headers=self._config.headers,
            timeout=30,
        )
        res.raise_for_status()
        return res.json()["hostname"]

    def __enter__(self) -> "Sandbox":
        return self

    def __exit__(self, *_: Any) -> None:
        self.kill()

    def fork(self, *, count: int = 1, timeout_ms: int = 0):
        """Fork is unsupported on Kubernetes; the backend returns HTTP 501."""
        from ..platform.client import PlatformClient
        return PlatformClient(self._config).post(f"/api/sandboxes/{self.sandbox_id}/fork", {"count": count, "timeoutMs": timeout_ms})

    def snapshot(self, name: str | None = None, *, pool_size: int = 5) -> SandboxSnapshot:
        """Capture memory and workspace. Disconnect active clients before capture."""
        from ..platform.client import PlatformClient
        return PlatformClient(self._config).post(f"/api/sandboxes/{self.sandbox_id}/snapshot", {"name": name if name is not None else f"Snapshot {self.sandbox_id}", "poolSize": pool_size})

    def wait_for_status(self, status: Literal["paused", "running"], *, wait_timeout_ms: int = 600_000) -> SandboxInfo:
        from ..errors import ConflictError, TimeoutError
        deadline = time.monotonic() + wait_timeout_ms / 1000
        while True:
            info = self.get_info()
            if info.status == status:
                return info
            if info.pause_error or info.status in ("failed", "stopped", "deleted"):
                raise ConflictError(info.pause_error or f"Sandbox is {info.status}")
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Sandbox did not become {status} within the wait timeout")
            time.sleep(min(1, max(0, deadline - time.monotonic())))

    def unexpose(self, port: int) -> None:
        from ..platform.client import PlatformClient
        PlatformClient(self._config).delete(f"/api/sandboxes/{self.sandbox_id}/expose/{port}")

    def logs(self, *, tail: int | None = None):
        from ..platform.client import PlatformClient, query
        return PlatformClient(self._config).events(query(f"/api/sandboxes/{self.sandbox_id}/logs", tail=tail))

    @classmethod
    def snapshots(cls, project_id: str, *, api_key: str | None = None, api_url: str | None = None) -> list[SandboxSnapshot]:
        from ..platform.client import PlatformClient, segment
        return PlatformClient(ConnectionConfig(api_key=api_key, api_url=api_url)).get(f"/api/projects/{segment(project_id)}/snapshots")

    @classmethod
    def get_snapshot(cls, snapshot_id: str, *, api_key: str | None = None, api_url: str | None = None) -> SandboxSnapshot:
        from ..platform.client import PlatformClient, segment
        return PlatformClient(ConnectionConfig(api_key=api_key, api_url=api_url)).get(f"/api/sandbox-snapshots/{segment(snapshot_id)}")

    @classmethod
    def restore(cls, snapshot_id: str, *, timeout_ms: int = DEFAULT_SANDBOX_TIMEOUT_MS, api_key: str | None = None, api_url: str | None = None) -> "Sandbox":
        """Claim a warm copy in the snapshot's project and region."""
        from ..platform.client import PlatformClient
        client = PlatformClient(ConnectionConfig(api_key=api_key, api_url=api_url))
        snapshot = cls.get_snapshot(snapshot_id, api_key=api_key, api_url=api_url)
        result = client.post("/api/sandboxes", {"snapshotId": snapshot_id, "projectId": snapshot["projectId"], "region": snapshot["region"], "timeoutMs": timeout_ms})
        return cls(result.get("sandboxId") or result["id"], api_key=api_key, api_url=api_url)

    @classmethod
    def set_snapshot_warm_pool(cls, snapshot_id: str, pool_size: int, *, api_key: str | None = None, api_url: str | None = None) -> SandboxSnapshot:
        from ..platform.client import PlatformClient, segment
        return PlatformClient(ConnectionConfig(api_key=api_key, api_url=api_url)).patch(f"/api/sandbox-snapshots/{segment(snapshot_id)}", {"poolSize": pool_size})

    @classmethod
    def pause_snapshot(cls, snapshot_id: str, *, api_key: str | None = None, api_url: str | None = None) -> SandboxSnapshot:
        """Release idle warm copies, preserving saved state and claimed sandboxes."""
        from ..platform.client import PlatformClient, segment
        return PlatformClient(ConnectionConfig(api_key=api_key, api_url=api_url)).post(f"/api/sandbox-snapshots/{segment(snapshot_id)}/pause", {})

    @classmethod
    def resume_snapshot(cls, snapshot_id: str, *, api_key: str | None = None, api_url: str | None = None) -> SandboxSnapshot:
        from ..platform.client import PlatformClient, segment
        return PlatformClient(ConnectionConfig(api_key=api_key, api_url=api_url)).post(f"/api/sandbox-snapshots/{segment(snapshot_id)}/resume", {})

    @classmethod
    def wait_for_snapshot(cls, snapshot_id: str, *, wait_timeout_ms: int = 900_000, api_key: str | None = None, api_url: str | None = None) -> SandboxSnapshot:
        from ..errors import ConflictError, TimeoutError
        deadline = time.monotonic() + wait_timeout_ms / 1000
        while True:
            snapshot = cls.get_snapshot(snapshot_id, api_key=api_key, api_url=api_url)
            if snapshot["status"] == "ready":
                return snapshot
            if snapshot["status"] in ("failed", "paused", "suspended"):
                raise ConflictError(snapshot.get("error") or f"Snapshot is {snapshot['status']}")
            if time.monotonic() >= deadline:
                raise TimeoutError("Snapshot did not become ready within the wait timeout")
            time.sleep(min(1, max(0, deadline - time.monotonic())))

    @classmethod
    def delete_snapshot(cls, snapshot_id: str, *, api_key: str | None = None, api_url: str | None = None):
        from ..platform.client import PlatformClient, segment
        return PlatformClient(ConnectionConfig(api_key=api_key, api_url=api_url)).delete(f"/api/sandbox-snapshots/{segment(snapshot_id)}")
