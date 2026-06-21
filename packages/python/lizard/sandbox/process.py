from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import ConnectionConfig


@dataclass
class ProcessResult:
    """Result of a process executed inside a Lizard sandbox microVM."""

    stdout: str
    stderr: str
    exit_code: int


class Process:
    """
    Run processes inside a Lizard sandbox microVM.

    Access via ``sandbox.process``.
    """

    def __init__(self, sandbox_id: str, config: "ConnectionConfig"):
        self._sandbox_id = sandbox_id
        self._config = config

    def exec_(
        self,
        cmd: str,
        *,
        envs: dict[str, str] | None = None,
        user: str | None = None,
        workdir: str | None = None,
        timeout_ms: int | None = None,
    ) -> ProcessResult:
        """
        Execute a command inside the microVM and wait for it to finish.

        The command runs in a shell inside the Lizard sandbox and returns
        stdout, stderr, and the exit code when it completes.

        :param cmd: Shell command to run inside the microVM.
        :param envs: Additional environment variables for this execution.
        :param user: Run as this Linux user (default: ``root``).
        :param workdir: Working directory inside the microVM.
        :param timeout_ms: Execution timeout in milliseconds.

        Example::

            result = sandbox.process.exec_("node index.js")
            print(result.stdout)

        Example with options::

            result = sandbox.process.exec_(
                "npm test",
                workdir="/app",
                envs={"NODE_ENV": "test"},
            )
        """
        import httpx

        body: dict = {"cmd": cmd}
        if envs:
            body["envs"] = envs
        if user:
            body["user"] = user
        if workdir:
            body["workdir"] = workdir
        if timeout_ms:
            body["timeoutMs"] = timeout_ms

        timeout = (timeout_ms or 60_000) / 1000

        res = httpx.post(
            f"{self._config.api_url}/api/sandboxes/{self._sandbox_id}/exec",
            headers=self._config.headers,
            json=body,
            timeout=timeout,
        )

        if not res.is_success:
            from ..errors import handle_api_error
            handle_api_error(res.status_code, res.text)

        data = res.json()
        return ProcessResult(
            stdout=data.get("stdout", ""),
            stderr=data.get("stderr", ""),
            exit_code=data.get("exitCode", 0),
        )
