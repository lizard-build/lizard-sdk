from __future__ import annotations
from dataclasses import dataclass
from typing import Any

from ..config import ConnectionConfig, HTTP_TIMEOUT_S, DEFAULT_SANDBOX_TIMEOUT_MS
from .process import Process
from .fs import Fs


@dataclass
class SandboxInfo:
    sandbox_id: str
    template: str
    started_at: str
    end_at: str
    #: Region the sandbox runs in -- the volume's region when one is attached.
    region: str | None = None
    status: str | None = None
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
        cpus=s.get("cpus"),
        memory_mb=s.get("memoryMb"),
        metadata=s.get("metadata"),
    )


class Sandbox:
    """
    A Lizard sandbox — an isolated Linux environment that starts in under a second.

    Each sandbox is a full Linux environment with its own filesystem, network, and
    process namespace, restored from a pre-warmed template snapshot.

    Sandboxes are **ephemeral**: killing one, or letting it hit its timeout,
    discards everything written inside it. State that has to outlive a sandbox
    belongs on a :class:`~lizard.Volume`, a separate disk mounted at ``/data``
    that a later sandbox can re-attach.

    Example::

        from lizard import Sandbox

        sandbox = Sandbox.create("base", project="my-project")
        sandbox.fs.write("/app/index.js", 'console.log("hello world")')
        result = sandbox.process.exec_("node /app/index.js")
        print(result.stdout)  # "hello world"
        sandbox.kill()

    Can also be used as a context manager::

        with Sandbox.create("code-interpreter-v1", project="my-project") as sandbox:
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

        Available templates: ``base`` (Debian + Node.js 26) and
        ``code-interpreter-v1`` (Python 3.14 + Node.js 26). Custom templates
        can be built and pushed via ``lizard push``.

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
            ``/data``. A volume's name is its key inside a project, so this is
            usually what you want. Requires an exact ``project_id``.
        :param volume_id: Attach a persistent volume by id, mounted at ``/data``
            inside the microVM. See :class:`lizard.Volume`.
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
        effective_timeout = timeout_ms or cls._default_timeout_ms
        resolved_project_id = exact_id or resolve_project_id(project_ref, config)

        body: dict[str, Any] = {
            "template": effective_template,
            "timeoutMs": effective_timeout,
            "projectId": resolved_project_id,
        }
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

        This used to call ``resume`` first, on the assumption that a sandbox you
        are reconnecting to might be paused. Sandboxes are pods now and
        pause/resume is a ``501`` on every one of them, so that call turned every
        ``connect()`` into an error against a perfectly healthy sandbox.
        Connecting does not need to change a sandbox's state, so it no longer
        tries to.

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
    def list(cls, *, api_key: str | None = None, api_url: str | None = None) -> list[SandboxInfo]:
        """List all running sandboxes for the authenticated account."""
        import httpx

        config = ConnectionConfig(api_key=api_key, api_url=api_url)
        res = httpx.get(f"{config.api_url}/api/sandboxes", headers=config.headers, timeout=HTTP_TIMEOUT_S)
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

        :returns: ``True`` if the microVM was terminated, ``False`` if it was already gone.
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
        """
        Pause the sandbox by freezing it in place.

        .. deprecated::
            Not implemented for the current runtime -- always raises
            :class:`~lizard.LizardError` with HTTP 501. Sandboxes run as pods, and
            the equivalent is a CRIU checkpoint of the pod, which is not built. To
            park work across a gap, put it on a :class:`~lizard.Volume` and create
            a fresh sandbox on that volume later; the volume is the part that is
            meant to outlive a sandbox.
        """
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
        """
        Resume a paused sandbox.

        .. deprecated::
            Not implemented for the current runtime -- always raises
            :class:`~lizard.LizardError` with HTTP 501. See :meth:`pause`.
            :meth:`Sandbox.connect` no longer calls this, so reconnecting to a
            running sandbox works without it.
        """
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

        :param port: Port number the service is listening on inside the microVM.

        Example::

            sandbox.process.exec_("npx -y serve -p 3000 &")
            url = sandbox.get_host(3000)
            # {sandboxId}-3000.sandbox.{region}.onlizard.com
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
