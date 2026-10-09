from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Literal, TypedDict
import time

from ..config import ConnectionConfig, HTTP_TIMEOUT_S, DEFAULT_SANDBOX_TIMEOUT_MS
from .process import Process
from .fs import Fs
from .desktop import Desktop


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
    #: Unix milliseconds.
    createdAt: int


@dataclass
class ExposedPort:
    """A sandbox port published on a public HTTPS hostname. See :meth:`Sandbox.expose_port`."""

    #: Hostname without a scheme, e.g. ``abc-3000.sandbox.eu-west-lim-a.onlizard.com``.
    hostname: str
    #: A browser URL that carries the access token (``?lizard_token=...``).
    url: str
    port: int
    #: The port is private: every request needs this token, either as the
    #: ``X-Lizard-Access-Token`` header or once as ``?lizard_token=`` (a browser
    #: then gets a cookie).
    access_token: str


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
    #: The sandbox runtime: ``"firecracker"`` (a microVM), ``"container"``, or None when unknown.
    runtime: str | None = None
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
        runtime=s.get("runtime"),
        size=s.get("size"),
        price_per_hour=s.get("pricePerHour"),
        cpus=s.get("cpus"),
        memory_mb=s.get("memoryMb"),
        metadata=s.get("metadata"),
    )


@dataclass
class ForkResult:
    """One entry of :meth:`Sandbox.fork`'s result: the new sandbox, or why that
    copy could not be made (e.g. the account's sandbox limit)."""

    sandbox: "Sandbox | None" = None
    info: SandboxInfo | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.sandbox is not None


class Sandbox:
    """
    A Linux sandbox: a Firecracker microVM with its own kernel.

    Run commands, read and write files, and expose HTTP ports in a sandbox. A
    sandbox boots in well under a second; :meth:`pause` and :meth:`resume` keep its
    memory and running processes, :meth:`snapshot` saves it in about 2 s and
    :meth:`restore` starts a copy in about 0.4 s, and :meth:`fork` clones a running
    sandbox, processes and all.

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
        #: The token that opens this sandbox's published ports. Set by
        #: :meth:`get_host` and :meth:`expose_port`; send it as the
        #: ``X-Lizard-Access-Token`` header.
        self.access_token: str | None = None
        self._pc = None
        self.fs = Fs(self.sandbox_id, self._config)
        self.process = Process(self.sandbox_id, self._config)
        #: Drive the graphical desktop of a ``desktop``-template sandbox: stream it to
        #: a browser, take screenshots, click and type. See :class:`Desktop`.
        self.desktop = Desktop(self.sandbox_id, self._config, self.process, self.fs)

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
        Use ``base`` for shell commands, ``interpreter`` for Python with the data
        stack (use :class:`~lizard.CodeSandbox` to run code snippets in it), or
        ``desktop`` for a graphical desktop.

        Every sandbox must belong to a project — billing is metered per project.
        Pass ``project`` (its ID, slug, or name) or an exact ``project_id``, or
        create sandboxes through a :class:`~lizard.Lizard` client, which pins the
        project for you.

        :param template: Template name. Defaults to ``base``.
        :param snapshot_id: Create from a private saved snapshot. The sandbox runs
            on the machine the snapshot was captured on and is billed by measured
            usage; ``size`` is ignored.
        :param size: Machine size, billed flat per hour (per second of running
            time): ``"small"`` (2 vCPU / 4 GB, $0.018/h), ``"medium"`` (4 vCPU /
            8 GB, $0.036/h, the default) or ``"large"`` (8 vCPU / 16 GB,
            $0.072/h). Measured CPU/RAM are not charged and egress is free;
            attached volumes bill separately.
        :param project: Project ID, slug, or name the sandbox belongs to.
        :param metadata: Your own key/value labels for the sandbox, returned by
            :meth:`get_info` and :meth:`list`.
        :param envs: Environment variables set in the sandbox, visible to every
            command it runs.
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
        """Pause the sandbox: its memory, running processes and files are kept and
        compute stops. Wait with ``wait_for_status("paused")`` before resuming."""
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
        """Resume a paused sandbox exactly where it stopped, processes included.
        Wait with ``wait_for_status("running")`` before running commands."""
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
        Publish a port on a public HTTPS hostname and return the hostname
        (without scheme).

        The port is private: requests need :attr:`access_token` (set by this
        call) as the ``X-Lizard-Access-Token`` header, or ``?lizard_token=<token>``
        in a browser. :meth:`expose_port` returns the token and a ready-made
        browser URL together.

        :param port: Port number the service is listening on inside the sandbox.

        Example::

            # Start an HTTP server on port 3000 before exposing it.
            hostname = sandbox.get_host(3000)
            httpx.get(f"https://{hostname}/", headers={"X-Lizard-Access-Token": sandbox.access_token})
        """
        return self.expose_port(port).hostname

    def expose_port(self, port: int) -> ExposedPort:
        """
        Publish a port and return everything needed to reach it: the hostname, a
        browser ``url`` that carries the token, and the ``access_token`` for API
        clients.

        Example::

            exposed = sandbox.expose_port(3000)
            print(exposed.url)  # open in a browser
            httpx.get(f"https://{exposed.hostname}/api",
                      headers={"X-Lizard-Access-Token": exposed.access_token})
        """
        import httpx

        res = httpx.post(
            f"{self._config.api_url}/api/sandboxes/{self.sandbox_id}/expose/{port}",
            headers=self._config.headers,
            timeout=HTTP_TIMEOUT_S,
        )
        if not res.is_success:
            from ..errors import handle_api_error
            handle_api_error(res.status_code, res.text)
        body = res.json()
        token = body.get("accessToken") or ""
        if token:
            self.access_token = token
        return ExposedPort(
            hostname=body["hostname"],
            url=body.get("url") or f"https://{body['hostname']}",
            port=body.get("port", port),
            access_token=token,
        )

    def _platform(self):
        """This sandbox's HTTP client, reused across calls (one connection pool)."""
        from ..platform.client import PlatformClient
        if self._pc is None:
            self._pc = PlatformClient(self._config)
        return self._pc

    def __enter__(self) -> "Sandbox":
        return self

    def __exit__(self, *_: Any) -> None:
        try:
            self.kill()
        finally:
            self.close()

    def fork(self, *, count: int = 1, timeout_ms: int = 0) -> "list[ForkResult]":
        """Clone this running sandbox ``count`` times (1-10).

        Each fork is a copy of the microVM at this instant -- memory, running
        processes and files -- and is billed like its source. The source keeps
        running.

        Returns one :class:`ForkResult` per requested fork, in order: its
        ``sandbox`` (a handle like this one) and ``info``, or ``error`` for a copy
        that could not be made (e.g. the account's sandbox limit). A sandbox with
        a volume attached cannot be forked (:class:`~lizard.ConflictError`, 409).

        :param timeout_ms: Lifetime of each fork; 0 (the default) uses the
            source's timeout.

        Example::

            for f in sandbox.fork(count=2):
                if f.sandbox:
                    f.sandbox.process.exec_("echo hi")
        """
        result = self._platform().post(f"/api/sandboxes/{self.sandbox_id}/fork", {"count": count, "timeoutMs": timeout_ms})
        out: list[ForkResult] = []
        for entry in result if isinstance(result, list) else []:
            info = entry.get("sandbox") if isinstance(entry, dict) else None
            sid = (info or {}).get("sandboxId") or (info or {}).get("id")
            if not sid:
                out.append(ForkResult(error=(entry or {}).get("error") or "fork failed"))
                continue
            out.append(ForkResult(
                sandbox=type(self)(sid, api_key=self._config.api_key, api_url=self._config.api_url),
                info=_to_sandbox_info({**info, "sandboxId": sid}),
            ))
        return out

    def snapshot(self, name: str | None = None, *, pool_size: int = 5) -> SandboxSnapshot:
        """Save this sandbox -- memory, running processes and files -- as a private
        snapshot.

        A Firecracker snapshot is ``ready`` as soon as this returns (about 2 s);
        start copies of it with :meth:`restore` (about 0.4 s each). The source keeps
        running. ``pool_size`` applies to container sandboxes only.
        """
        return self._platform().post(f"/api/sandboxes/{self.sandbox_id}/snapshot", {"name": name if name is not None else f"Snapshot {self.sandbox_id}", "poolSize": pool_size})

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
        """Unpublish a port exposed with :meth:`get_host` / :meth:`expose_port`."""
        self._platform().delete(f"/api/sandboxes/{self.sandbox_id}/expose/{port}")

    def logs(self, *, tail: int | None = None):
        """Stream the sandbox's logs. Not available on Firecracker sandboxes yet
        (:class:`~lizard.LizardError`, 501)."""
        from ..platform.client import query
        return self._platform().events(query(f"/api/sandboxes/{self.sandbox_id}/logs", tail=tail))

    def close(self) -> None:
        """Release this handle's HTTP connections. The sandbox keeps running."""
        for owner in (self, self.desktop):
            pc = getattr(owner, "_pc", None)
            if pc is not None:
                pc.close()
                owner._pc = None

    @classmethod
    def snapshots(cls, project_id: str, *, api_key: str | None = None, api_url: str | None = None) -> list[SandboxSnapshot]:
        from ..platform.client import PlatformClient, segment
        with PlatformClient(ConnectionConfig(api_key=api_key, api_url=api_url)) as pc:
            return pc.get(f"/api/projects/{segment(project_id)}/snapshots")

    @classmethod
    def get_snapshot(cls, snapshot_id: str, *, api_key: str | None = None, api_url: str | None = None) -> SandboxSnapshot:
        from ..platform.client import PlatformClient, segment
        with PlatformClient(ConnectionConfig(api_key=api_key, api_url=api_url)) as pc:
            return pc.get(f"/api/sandbox-snapshots/{segment(snapshot_id)}")

    @classmethod
    def restore(cls, snapshot_id: str, *, timeout_ms: int = DEFAULT_SANDBOX_TIMEOUT_MS, api_key: str | None = None, api_url: str | None = None) -> "Sandbox":
        """Start a new sandbox from a snapshot, in the snapshot's project and region."""
        from ..platform.client import PlatformClient
        snapshot = cls.get_snapshot(snapshot_id, api_key=api_key, api_url=api_url)
        with PlatformClient(ConnectionConfig(api_key=api_key, api_url=api_url)) as client:
            result = client.post("/api/sandboxes", {"snapshotId": snapshot_id, "projectId": snapshot["projectId"], "region": snapshot["region"], "timeoutMs": timeout_ms})
        return cls(result.get("sandboxId") or result["id"], api_key=api_key, api_url=api_url)

    @classmethod
    def set_snapshot_warm_pool(cls, snapshot_id: str, pool_size: int, *, api_key: str | None = None, api_url: str | None = None) -> SandboxSnapshot:
        from ..platform.client import PlatformClient, segment
        with PlatformClient(ConnectionConfig(api_key=api_key, api_url=api_url)) as pc:
            return pc.patch(f"/api/sandbox-snapshots/{segment(snapshot_id)}", {"poolSize": pool_size})

    @classmethod
    def pause_snapshot(cls, snapshot_id: str, *, api_key: str | None = None, api_url: str | None = None) -> SandboxSnapshot:
        """Release idle warm copies (container snapshots), preserving saved state and claimed sandboxes."""
        from ..platform.client import PlatformClient, segment
        with PlatformClient(ConnectionConfig(api_key=api_key, api_url=api_url)) as pc:
            return pc.post(f"/api/sandbox-snapshots/{segment(snapshot_id)}/pause", {})

    @classmethod
    def resume_snapshot(cls, snapshot_id: str, *, api_key: str | None = None, api_url: str | None = None) -> SandboxSnapshot:
        from ..platform.client import PlatformClient, segment
        with PlatformClient(ConnectionConfig(api_key=api_key, api_url=api_url)) as pc:
            return pc.post(f"/api/sandbox-snapshots/{segment(snapshot_id)}/resume", {})

    @classmethod
    def wait_for_snapshot(cls, snapshot_id: str, *, wait_timeout_ms: int = 900_000, api_key: str | None = None, api_url: str | None = None) -> SandboxSnapshot:
        from ..errors import ConflictError, TimeoutError
        deadline = time.monotonic() + wait_timeout_ms / 1000
        while True:
            snapshot = cls.get_snapshot(snapshot_id, api_key=api_key, api_url=api_url)
            if snapshot["status"] == "ready" and snapshot.get("readyCount", 0) >= max(1, snapshot.get("poolSize", 1)):
                return snapshot
            if snapshot["status"] in ("failed", "paused", "suspended"):
                raise ConflictError(snapshot.get("error") or f"Snapshot is {snapshot['status']}")
            if time.monotonic() >= deadline:
                raise TimeoutError("Snapshot did not become ready within the wait timeout")
            time.sleep(min(1, max(0, deadline - time.monotonic())))

    @classmethod
    def delete_snapshot(cls, snapshot_id: str, *, api_key: str | None = None, api_url: str | None = None):
        from ..platform.client import PlatformClient, segment
        with PlatformClient(ConnectionConfig(api_key=api_key, api_url=api_url)) as pc:
            return pc.delete(f"/api/sandbox-snapshots/{segment(snapshot_id)}")
