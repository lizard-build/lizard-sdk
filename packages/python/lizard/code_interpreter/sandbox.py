from __future__ import annotations

import json
from typing import Callable, Iterator, Optional

import httpx

from ..sandbox.sandbox import Sandbox
from .types import (
    CodeContext,
    Execution,
    ExecutionError,
    OutputItem,
    ResultItem,
    StdoutItem,
    StderrItem,
    ErrorItem,
)

_CODE_INTERPRETER_PORT = 8080


class CodeSandbox(Sandbox):
    """
    A Lizard sandbox with built-in stateful code execution.

    Extends the base Sandbox with ``run_code()`` — executes code in a
    persistent kernel so variables and imports survive between calls.

    Supports Python, JavaScript (Node.js), and Bash out of the box.

    Example::

        with CodeSandbox.create() as sandbox:
            sandbox.run_code("x = 42")
            result = sandbox.run_code("print(x * 2)")
            print(result.stdout)  # "84\\n"

    Example — JavaScript::

        result = sandbox.run_code("1 + 1", language="javascript")
        print(result.results[0].data)  # "2"
    """

    _DEFAULT_TEMPLATE = "code-interpreter-v1"

    @property
    def _server_url(self) -> str:
        return f"https://{self.get_host(_CODE_INTERPRETER_PORT)}"

    def run_code(
        self,
        code: str,
        *,
        language: str | None = None,
        context: CodeContext | None = None,
        envs: dict[str, str] | None = None,
        timeout_ms: int = 60_000,
        on_stdout: Callable[[str], None] | None = None,
        on_stderr: Callable[[str], None] | None = None,
        on_result: Callable[[ResultItem], None] | None = None,
        on_error: Callable[[ExecutionError], None] | None = None,
    ) -> Execution:
        """
        Execute code in a persistent kernel.

        Variables, imports, and function definitions from previous calls are
        available in subsequent calls within the same context.

        :param code: Source code to run.
        :param language: ``'python'``, ``'javascript'``, or ``'bash'``.
            Defaults to ``'python'``.
        :param context: Run in a specific context instead of the default one.
        :param envs: Extra environment variables available to the code.
        :param timeout_ms: Timeout in milliseconds. Default 60 000.
        :param on_stdout: Callback invoked for each stdout chunk.
        :param on_stderr: Callback invoked for each stderr chunk.
        :param on_result: Callback invoked for each rich result item.
        :param on_error: Callback invoked if the code throws an exception.
        :returns: :class:`Execution` with stdout, stderr, results, and error.
        """
        if context and language:
            raise ValueError("Provide context or language, not both")

        body: dict = {"code": code, "env_vars": envs or {}}
        if context:
            body["context_id"] = context.id
        elif language:
            body["language"] = language

        execution = Execution()

        with httpx.stream(
            "POST",
            f"{self._server_url}/execute",
            json=body,
            timeout=timeout_ms / 1000,
        ) as resp:
            resp.raise_for_status()

            for raw in resp.iter_lines():
                if not raw.strip():
                    continue
                try:
                    item = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                t = item.get("type")

                if t == "stdout":
                    execution.stdout += item["data"]
                    on_stdout and on_stdout(item["data"])

                elif t == "stderr":
                    execution.stderr += item["data"]
                    on_stderr and on_stderr(item["data"])

                elif t == "result":
                    r = ResultItem(mime=item.get("mime", "text/plain"), data=item.get("data", ""))
                    execution.results.append(r)
                    on_result and on_result(r)

                elif t == "error":
                    err = ExecutionError(
                        name=item.get("name", "Error"),
                        message=item.get("message", ""),
                        traceback=item.get("traceback", ""),
                    )
                    execution.error = err
                    on_error and on_error(err)

                elif t == "done":
                    execution.execution_count = item.get("execution_count", 0)
                    break

        return execution

    def create_context(
        self,
        language: str = "python",
        cwd: str = "/home/user",
    ) -> CodeContext:
        """Create a new isolated execution context."""
        resp = httpx.post(
            f"{self._server_url}/contexts",
            json={"language": language, "cwd": cwd},
        )
        resp.raise_for_status()
        data = resp.json()
        return CodeContext(**data)

    def list_contexts(self) -> list[CodeContext]:
        """List all active contexts in this sandbox."""
        resp = httpx.get(f"{self._server_url}/contexts")
        resp.raise_for_status()
        return [CodeContext(**c) for c in resp.json()]

    def delete_context(self, context: CodeContext | str) -> None:
        """Delete a context and free its resources."""
        ctx_id = context if isinstance(context, str) else context.id
        resp = httpx.delete(f"{self._server_url}/contexts/{ctx_id}")
        resp.raise_for_status()

    def restart_context(self, context: CodeContext | str) -> None:
        """Restart a context, clearing all variables and state."""
        ctx_id = context if isinstance(context, str) else context.id
        resp = httpx.post(f"{self._server_url}/contexts/{ctx_id}/restart")
        resp.raise_for_status()
