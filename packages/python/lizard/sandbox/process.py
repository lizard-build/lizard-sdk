from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, TYPE_CHECKING

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
        on_stdout: "Callable[[str], None] | None" = None,
        on_stderr: "Callable[[str], None] | None" = None,
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
        :param on_stdout: Called with each stdout line as it is produced, rather
            than at the end. Passing it switches the call to a streaming read.
        :param on_stderr: Called with each stderr line as it is produced.

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

        if on_stdout is not None or on_stderr is not None:
            return self._exec_streaming(body, timeout, on_stdout, on_stderr)

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

    def _exec_streaming(
        self,
        body: dict,
        timeout: float,
        on_stdout: "Callable[[str], None] | None",
        on_stderr: "Callable[[str], None] | None",
    ) -> ProcessResult:
        """Read the exec output as an SSE stream, handing each line to the caller as
        it arrives while still accumulating the full result.

        The platform has always streamed exec output; it just has to be asked for it
        with an SSE Accept header. Events are ``{"stream", "line"}`` for output and
        ``{"exitCode"}`` at the end.
        """
        import httpx
        import json as _json

        headers = dict(self._config.headers)
        headers["Accept"] = "text/event-stream"

        stdout_parts: list[str] = []
        stderr_parts: list[str] = []
        exit_code = 0

        with httpx.stream(
            "POST",
            f"{self._config.api_url}/api/sandboxes/{self._sandbox_id}/exec",
            headers=headers,
            json=body,
            timeout=timeout,
        ) as res:
            if not res.is_success:
                res.read()
                from ..errors import handle_api_error
                handle_api_error(res.status_code, res.text)
            for raw in res.iter_lines():
                if not raw.startswith("data:"):
                    continue
                try:
                    ev = _json.loads(raw[5:].strip())
                except ValueError:
                    continue  # a partial or non-JSON keepalive frame
                line = ev.get("line")
                if line is not None:
                    if ev.get("stream") == "stderr":
                        stderr_parts.append(line)
                        if on_stderr is not None:
                            on_stderr(line)
                    else:
                        stdout_parts.append(line)
                        if on_stdout is not None:
                            on_stdout(line)
                if ev.get("exitCode") is not None:
                    exit_code = ev["exitCode"]

        return ProcessResult(
            stdout="\n".join(stdout_parts),
            stderr="\n".join(stderr_parts),
            exit_code=exit_code,
        )
