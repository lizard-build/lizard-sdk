from __future__ import annotations

import base64
import json
import uuid
from typing import Any, Callable

from ..errors import LizardError
from ..sandbox.sandbox import Sandbox
from ._runner import SOURCE as _RUNNER_SOURCE
from .types import (
    CodeContext,
    Execution,
    ExecutionError,
    ResultItem,
)

#: Default execution timeout for :meth:`CodeSandbox.run_code`, milliseconds.
_DEFAULT_RUN_TIMEOUT_MS = 60_000
#: Extra time the exec call gets on top of the code's own timeout (kernel start-up).
_RUNNER_OVERHEAD_MS = 45_000
#: Encoded arguments above this go through a file instead of argv (128 KiB per-argument limit).
_MAX_INLINE_ARGS = 100_000


class CodeSandbox(Sandbox):
    """
    A sandbox for running code snippets, built on :attr:`Sandbox.process`.

    Boots the ``interpreter`` template by default. Python runs in a persistent
    Jupyter kernel per context, so variables, imports and functions carry over
    between calls, ``execution.results`` holds rich output (the value of the
    last expression, matplotlib charts as ``image/png``, HTML, ...) and errors
    carry the exception name and traceback.

    Limits, honestly:

    - ``javascript`` (node) and ``bash`` run each call as a fresh process: no
      state carries over and ``results`` stays empty. ``node`` must be installed
      in the template; the ``interpreter`` template does not ship it.
    - On a template without Jupyter (e.g. ``base``), Python also runs as a fresh
      process per call.
    - ``stdout``/``stderr`` are delivered in the chunks the kernel or process
      produced them, not per character.

    Kernels live inside the sandbox's microVM, so pause/resume, snapshots and
    forks keep their state.

    Example::

        with CodeSandbox.create(project="my-project") as sandbox:
            sandbox.run_code("x = 21")
            run = sandbox.run_code("x * 2")
            print(run.results[0].data)  # "42"
    """

    _default_template = "interpreter"

    def run_code(
        self,
        code: str,
        *,
        language: str | None = None,
        context: CodeContext | None = None,
        envs: dict[str, str] | None = None,
        timeout_ms: int = _DEFAULT_RUN_TIMEOUT_MS,
        on_stdout: Callable[[str], None] | None = None,
        on_stderr: Callable[[str], None] | None = None,
        on_result: Callable[[ResultItem], None] | None = None,
        on_error: Callable[[ExecutionError], None] | None = None,
    ) -> Execution:
        """
        Execute code and wait for it to finish.

        Python keeps its state per context (the default context, per language,
        when none is given). Code errors appear in ``execution.error``; request
        failures raise.

        :param code: Source code to run.
        :param language: ``'python'``, ``'javascript'``, or ``'bash'``.
            Defaults to ``'python'``.
        :param context: Run in a context from :meth:`create_context` instead of
            the per-language default.
        :param envs: Extra environment variables for this call.
        :param timeout_ms: Execution timeout in milliseconds, default 60 000. A
            Python kernel that runs past it is interrupted (its state is kept)
            and ``execution.error.name`` is ``"TimeoutError"``; a process is killed.
        :param on_stdout: Callback invoked for each stdout chunk.
        :param on_stderr: Callback invoked for each stderr chunk.
        :param on_result: Callback invoked for each rich result item.
        :param on_error: Callback invoked if the code raises an exception.
        :returns: :class:`Execution` with stdout, stderr, results, and error.

        Example::

            run = sandbox.run_code("import math\\nprint(math.sqrt(144))")
            print(run.stdout)  # "12.0\\n"
        """
        if context and language:
            raise ValueError("Provide context or language, not both")

        args: dict[str, Any] = {"action": "run", "code": code, "envs": envs or {}, "timeout": timeout_ms / 1000}
        if context:
            args["context"] = context.id
        else:
            args["language"] = language or "python"

        execution = Execution()

        def handle(item: dict) -> None:
            t = item.get("type")
            if t == "stdout":
                execution.stdout += item.get("data", "")
                on_stdout and on_stdout(item.get("data", ""))
            elif t == "stderr":
                execution.stderr += item.get("data", "")
                on_stderr and on_stderr(item.get("data", ""))
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
                execution.execution_count = item.get("execution_count", 0) or 0

        self._runner(args, timeout_ms, handle)
        return execution

    def create_context(
        self,
        language: str = "python",
        cwd: str = "/home/user",
    ) -> CodeContext:
        """Create a new isolated execution context.

        A Python context is its own kernel: its own variables, and ``cwd`` as its
        working directory. Other languages get the working directory only.
        """
        found: list[CodeContext] = []

        def handle(ev: dict) -> None:
            if ev.get("type") == "context":
                found.append(CodeContext(id=ev["id"], language=ev["language"], cwd=ev["cwd"]))

        self._runner({"action": "create", "id": f"ctx-{uuid.uuid4().hex[:16]}", "language": language, "cwd": cwd},
                     _DEFAULT_RUN_TIMEOUT_MS, handle)
        if not found:
            raise LizardError("Failed to create context")
        return found[0]

    def list_contexts(self) -> list[CodeContext]:
        """List the contexts created with :meth:`create_context` in this sandbox."""
        out: list[CodeContext] = []

        def handle(ev: dict) -> None:
            if ev.get("type") == "contexts":
                out.extend(CodeContext(id=c["id"], language=c["language"], cwd=c["cwd"]) for c in ev.get("data", []))

        self._runner({"action": "list"}, _DEFAULT_RUN_TIMEOUT_MS, handle)
        return out

    def delete_context(self, context: CodeContext | str) -> None:
        """Delete a context, stopping its kernel."""
        ctx_id = context if isinstance(context, str) else context.id
        self._runner({"action": "delete", "context": ctx_id}, _DEFAULT_RUN_TIMEOUT_MS, lambda _ev: None)

    def restart_context(self, context: CodeContext | str) -> None:
        """Restart a context, clearing all variables and state."""
        ctx_id = context if isinstance(context, str) else context.id
        self._runner({"action": "restart", "context": ctx_id}, _DEFAULT_RUN_TIMEOUT_MS, lambda _ev: None)

    def _runner(self, args: dict, timeout_ms: int, on_event: Callable[[dict], None]) -> None:
        """Run the in-sandbox runner with ``args`` and hand each of its events to ``on_event``."""
        encoded = base64.b64encode(json.dumps(args).encode()).decode("ascii")
        if len(encoded) > _MAX_INLINE_ARGS and isinstance(args.get("code"), str):
            code_file = f"/tmp/.lizard-code/in-{uuid.uuid4().hex[:16]}"
            self.fs.write(code_file, args["code"])
            rest = {k: v for k, v in args.items() if k != "code"}
            encoded = base64.b64encode(json.dumps({**rest, "codeFile": code_file}).encode()).decode("ascii")

        state: dict[str, Any] = {"part": "", "fatal": None, "saw": False}
        stderr: list[str] = []

        def on_line(line: str) -> None:
            try:
                ev = json.loads(line)
                # An event too long for one output line arrives as pieces.
                if isinstance(ev, dict) and ev.get("type") == "part":
                    state["part"] += ev.get("data", "")
                    if not ev.get("end"):
                        return
                    ev = json.loads(state["part"])
                    state["part"] = ""
            except ValueError:
                state["part"] = ""
                return
            if not isinstance(ev, dict):
                return
            state["saw"] = True
            if ev.get("type") == "fatal":
                state["fatal"] = ev.get("message", "code runner failed")
            else:
                on_event(ev)

        result = self.process.exec_(
            ["python3", "-c", _RUNNER_SOURCE, encoded],
            timeout_ms=timeout_ms + _RUNNER_OVERHEAD_MS,
            on_stdout=on_line,
            on_stderr=stderr.append,
        )
        if state["fatal"]:
            raise LizardError(state["fatal"])
        if result.exit_code != 0 or not state["saw"]:
            detail = "\n".join(stderr[-20:]).strip() or f"exit code {result.exit_code}"
            raise LizardError(f"Code runner failed (python3 is required in the sandbox): {detail}")
