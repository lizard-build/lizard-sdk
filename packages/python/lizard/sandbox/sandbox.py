from __future__ import annotations
from dataclasses import dataclass
from typing import Any

from ..config import ConnectionConfig, DEFAULT_SANDBOX_TIMEOUT_MS
from .process import Process
from .fs import Fs


@dataclass
class SandboxInfo:
    sandbox_id: str
    template: str
    started_at: str
    end_at: str
    metadata: dict[str, str] | None = None


class Sandbox:
    """
    A Lizard sandbox — an isolated Firecracker microVM that boots in milliseconds.

    Each sandbox is a full Linux environment with its own filesystem, network,
    and process namespace. Sandboxes are created from templates, can be paused
    to a snapshot, and resumed instantly — ideal for stateful AI agent sessions
    or ephemeral code execution.

    Example::

        from lizard import Sandbox

        sandbox = Sandbox.create("node22")
        sandbox.fs.write("/app/index.js", 'console.log("hello world")')
        result = sandbox.process.exec_("node /app/index.js")
        print(result.stdout)  # "hello world"
        sandbox.kill()

    Can also be used as a context manager::

        with Sandbox.create("python312") as sandbox:
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
        api_key: str | None = None,
        api_url: str | None = None,
        timeout_ms: int | None = None,
        metadata: dict[str, str] | None = None,
        envs: dict[str, str] | None = None,
    ) -> "Sandbox":
        """
        Boot a new Lizard sandbox from the specified template.

        Available templates include ``base``, ``node22``, and ``python312``.
        Custom templates can be built and pushed via ``lizard push``.

        :param template: Template name. Defaults to ``base``.

        Example::

            sandbox = Sandbox.create("node22")
            sandbox = Sandbox.create()  # uses 'base' template
        """
        import httpx

        config = ConnectionConfig(api_key=api_key, api_url=api_url, timeout_ms=timeout_ms)
        effective_template = template or cls._default_template
        effective_timeout = timeout_ms or cls._default_timeout_ms

        body: dict[str, Any] = {"template": effective_template, "timeoutMs": effective_timeout}
        if metadata:
            body["metadata"] = metadata
        if envs:
            body["envs"] = envs

        res = httpx.post(
            f"{config.api_url}/api/sandboxes",
            headers=config.headers,
            json=body,
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

        If the sandbox is currently paused, it is automatically resumed from
        its last snapshot before this call returns.

        Example::

            sandbox = Sandbox.connect("sandbox_abc123")
        """
        import httpx

        config = ConnectionConfig(api_key=api_key, api_url=api_url)
        res = httpx.post(
            f"{config.api_url}/api/sandboxes/{sandbox_id}/resume",
            headers=config.headers,
        )
        if res.status_code not in (200, 404):
            from ..errors import handle_api_error
            handle_api_error(res.status_code, res.text)

        return cls(sandbox_id, api_key=api_key, api_url=api_url)

    @classmethod
    def list(cls, *, api_key: str | None = None, api_url: str | None = None) -> list[SandboxInfo]:
        """List all running sandboxes for the authenticated account."""
        import httpx

        config = ConnectionConfig(api_key=api_key, api_url=api_url)
        res = httpx.get(f"{config.api_url}/api/sandboxes", headers=config.headers)
        if not res.is_success:
            from ..errors import handle_api_error
            handle_api_error(res.status_code, res.text)

        return [
            SandboxInfo(
                sandbox_id=s["sandboxId"],
                template=s["template"],
                started_at=s["startedAt"],
                end_at=s["endAt"],
                metadata=s.get("metadata"),
            )
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
        )
        if res.status_code == 404:
            return False
        if not res.is_success:
            from ..errors import handle_api_error
            handle_api_error(res.status_code, res.text)
        return True

    def pause(self) -> bool:
        """
        Snapshot and pause the sandbox microVM.

        The sandbox state — memory, filesystem, and running processes — is
        saved to a snapshot. Resume with :meth:`resume` or
        :meth:`Sandbox.connect`.

        :returns: ``True`` if paused successfully.
        """
        import httpx

        res = httpx.post(
            f"{self._config.api_url}/api/sandboxes/{self.sandbox_id}/pause",
            headers=self._config.headers,
        )
        if res.status_code == 404:
            return False
        if not res.is_success:
            from ..errors import handle_api_error
            handle_api_error(res.status_code, res.text)
        return True

    def resume(self) -> bool:
        """
        Resume a paused sandbox from its last snapshot.

        :returns: ``True`` if resumed successfully.
        """
        import httpx

        res = httpx.post(
            f"{self._config.api_url}/api/sandboxes/{self.sandbox_id}/resume",
            headers=self._config.headers,
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
        )
        if not res.is_success:
            from ..errors import handle_api_error
            handle_api_error(res.status_code, res.text)

        s = res.json()
        return SandboxInfo(
            sandbox_id=s["sandboxId"],
            template=s["template"],
            started_at=s["startedAt"],
            end_at=s["endAt"],
            metadata=s.get("metadata"),
        )

    def get_host(self, port: int) -> str:
        """
        Get the public HTTPS URL for a port exposed inside the sandbox.

        Useful for reaching HTTP servers started inside the microVM from your
        agent or tests without any additional tunneling.

        :param port: Port number the service is listening on inside the microVM.

        Example::

            sandbox.process.exec_("npx -y serve -p 3000 &")
            url = sandbox.get_host(3000)
            # https://{sandboxId}-3000.sandbox.lizard.run
        """
        from urllib.parse import urlparse
        api_host = urlparse(self._config.api_url).netloc
        base_host = api_host.replace("api.", "", 1)
        return f"{self.sandbox_id}-{port}.sandbox.{base_host}"

    def __enter__(self) -> "Sandbox":
        return self

    def __exit__(self, *_: Any) -> None:
        self.kill()
