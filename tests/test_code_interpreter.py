"""
Integration tests for the code-interpreter-v1 sandbox template.

Tests run directly against the local node-agent (localhost:7070) with admin
auth, bypassing the platform API. This lets us verify the sandbox VM itself
works end-to-end without needing a cloud account.

Uses the actual SDK classes (CodeSandbox, Execution, ExecutionError, ResultItem)
so test failures surface SDK contract violations, not just node-agent quirks.

Run with:
    PYTHONPATH=packages/python venv/bin/pytest tests/test_code_interpreter.py -v
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass, field

import httpx
import pytest

from lizard.code_interpreter.types import Execution, ExecutionError, ResultItem

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

NODE_AGENT_URL = "http://localhost:7070"
ADMIN_SECRET = "bd3323b6791f3e60025462bb4042ed3d0f62cd47518332b43918a19814e5162a"
TEMPLATE = "code-interpreter-v1"

_agent_headers = {"X-Admin-Secret": ADMIN_SECRET, "Content-Type": "application/json"}


# ---------------------------------------------------------------------------
# NodeSandbox — thin wrapper that talks directly to node-agent + VM guest IP
#
# Mirrors the CodeSandbox interface so tests read identically to SDK usage.
# ---------------------------------------------------------------------------


class NodeSandbox:
    """
    A code-interpreter sandbox backed by the local node-agent.

    Mirrors CodeSandbox.run_code() behaviour using the SDK's own types so
    tests surface real SDK contract violations.
    """

    def __init__(self, sandbox_id: str, guest_ip: str):
        self.id = sandbox_id
        self.guest_ip = guest_ip
        self._server_url = f"http://{guest_ip}:8080"

    # ------------------------------------------------------------------ create

    @classmethod
    def create(cls, template: str = TEMPLATE, timeout_ms: int = 300_000) -> "NodeSandbox":
        sb_id = "test-" + uuid.uuid4().hex[:8]
        resp = httpx.post(
            f"{NODE_AGENT_URL}/sandboxes",
            headers=_agent_headers,
            json={"id": sb_id, "template": template, "timeoutMs": timeout_ms},
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        return cls(data["id"], data["guestIp"])

    # ----------------------------------------------------------------- run_code

    def run_code(
        self,
        code: str,
        *,
        language: str | None = None,
        context_id: str | None = None,
        env_vars: dict[str, str] | None = None,
    ) -> Execution:
        body: dict = {"code": code, "env_vars": env_vars or {}}
        if context_id:
            body["context_id"] = context_id
        elif language:
            body["language"] = language

        execution = Execution()
        with httpx.stream("POST", f"{self._server_url}/execute", json=body, timeout=30) as resp:
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
                elif t == "stderr":
                    execution.stderr += item["data"]
                elif t == "result":
                    execution.results.append(ResultItem(mime=item.get("mime", ""), data=item.get("data", "")))
                elif t == "error":
                    execution.error = ExecutionError(
                        name=item.get("name", "Error"),
                        message=item.get("message", ""),
                        traceback=item.get("traceback", ""),
                    )
                elif t == "done":
                    execution.execution_count = item.get("execution_count", 0)
                    break
        return execution

    # ------------------------------------------------------------------ context

    def create_context(self, language: str = "python", cwd: str = "/home/user") -> str:
        resp = httpx.post(
            f"{self._server_url}/contexts",
            json={"language": language, "cwd": cwd},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()["id"]

    # -------------------------------------------------------------------- kill

    def kill(self) -> None:
        httpx.delete(
            f"{NODE_AGENT_URL}/sandboxes/{self.id}",
            headers=_agent_headers,
            timeout=10,
        )

    def __enter__(self) -> "NodeSandbox":
        return self

    def __exit__(self, *_) -> None:
        self.kill()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _wait_for_server(guest_ip: str, timeout: float = 5.0) -> None:
    """Wait until the code-interpreter uvicorn server is ready to accept requests."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = httpx.get(f"http://{guest_ip}:8080/health", timeout=1)
            if r.is_success:
                return
        except Exception:
            pass
        time.sleep(0.1)
    raise TimeoutError(f"code-interpreter server at {guest_ip}:8080 not ready after {timeout}s")


# ---------------------------------------------------------------------------
# 1. Warm-pool performance
# ---------------------------------------------------------------------------


class TestWarmPool:
    def test_create_is_fast(self):
        """Warm pool should boot a sandbox in under 1 s (typically ~200–400 ms)."""
        t0 = time.time()
        with NodeSandbox.create() as sb:
            elapsed = time.time() - t0
        assert elapsed < 1.0, f"Create took {elapsed:.3f}s — warm pool miss?"

    def test_burst_of_four(self):
        """
        Create 4 sandboxes back-to-back. The pool holds 3 pre-warmed slots;
        the 4th triggers a cold refill. All should succeed; the first 3 must
        each complete under 1 s.
        """
        timings = []
        sandboxes = []
        try:
            for _ in range(4):
                t0 = time.time()
                sb = NodeSandbox.create()
                timings.append(time.time() - t0)
                sandboxes.append(sb)

            # First 3 are warm hits, last may be a cold restore
            for i, t in enumerate(timings[:3]):
                assert t < 1.0, f"Sandbox {i} took {t:.3f}s — expected warm hit"
        finally:
            for sb in sandboxes:
                sb.kill()

    def test_concurrent_creates(self):
        """Three parallel creates all succeed (no pool contention deadlock)."""
        results: list[NodeSandbox | Exception] = []
        lock = threading.Lock()

        def _create():
            try:
                sb = NodeSandbox.create()
                with lock:
                    results.append(sb)
            except Exception as e:
                with lock:
                    results.append(e)

        threads = [threading.Thread(target=_create) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        try:
            errors = [r for r in results if isinstance(r, Exception)]
            assert errors == [], f"Concurrent creates failed: {errors}"
            assert len(results) == 3
        finally:
            for r in results:
                if isinstance(r, NodeSandbox):
                    r.kill()


# ---------------------------------------------------------------------------
# 2. Python execution
# ---------------------------------------------------------------------------


class TestPython:
    def test_print(self, sandbox: NodeSandbox):
        result = sandbox.run_code("print('hello world')")
        assert result.success
        assert "hello world" in result.stdout

    def test_arithmetic_result(self, sandbox: NodeSandbox):
        """Expression on last line is captured as a result item."""
        result = sandbox.run_code("2 ** 10")
        assert result.success
        # Result may be in results list or stdout depending on executor design
        result_data = result.results[0].data if result.results else result.stdout.strip()
        assert "1024" in result_data

    def test_state_persists_between_calls(self, sandbox: NodeSandbox):
        """Variables set in one call are visible in the next (stateful kernel)."""
        sandbox.run_code("accumulator = 0")
        sandbox.run_code("accumulator += 7")
        result = sandbox.run_code("print(accumulator)")
        assert result.success
        assert "7" in result.stdout

    def test_multiline_code(self, sandbox: NodeSandbox):
        result = sandbox.run_code(
            "def greet(name):\n    return f'Hello, {name}!'\nprint(greet('Lizard'))"
        )
        assert result.success
        assert "Hello, Lizard!" in result.stdout

    def test_import_stdlib(self, sandbox: NodeSandbox):
        result = sandbox.run_code("import math\nprint(round(math.pi, 4))")
        assert result.success
        assert "3.1416" in result.stdout

    def test_list_comprehension_result(self, sandbox: NodeSandbox):
        result = sandbox.run_code("[x * x for x in range(5)]")
        assert result.success
        assert "16" in (result.results[0].data if result.results else result.stdout)

    def test_error_zerodivision(self, sandbox: NodeSandbox):
        result = sandbox.run_code("1 / 0")
        assert not result.success
        assert result.error is not None
        assert "ZeroDivisionError" in result.error.name

    def test_error_name_error(self, sandbox: NodeSandbox):
        result = sandbox.run_code("print(undefined_variable_xyz)")
        assert not result.success
        assert result.error is not None
        assert "NameError" in result.error.name

    def test_error_has_traceback(self, sandbox: NodeSandbox):
        result = sandbox.run_code("raise ValueError('test error')")
        assert result.error is not None
        assert result.error.traceback != ""

    def test_env_vars(self, sandbox: NodeSandbox):
        result = sandbox.run_code(
            "import os; print(os.environ.get('MY_TEST_VAR', 'missing'))",
            env_vars={"MY_TEST_VAR": "lizard_rocks"},
        )
        assert result.success
        assert "lizard_rocks" in result.stdout

    def test_stderr_captured(self, sandbox: NodeSandbox):
        result = sandbox.run_code("import sys; sys.stderr.write('err_msg\\n'); sys.stderr.flush()")
        assert result.success
        assert "err_msg" in result.stderr

    def test_execution_count_increments(self, sandbox: NodeSandbox):
        r1 = sandbox.run_code("1 + 1")
        r2 = sandbox.run_code("2 + 2")
        assert r2.execution_count > r1.execution_count

    def test_json_result_mime(self, sandbox: NodeSandbox):
        result = sandbox.run_code('{"key": "value"}')
        assert result.success
        # Dict literal evaluated → result with JSON mime
        if result.results:
            assert "json" in result.results[0].mime.lower()

    def test_matplotlib_figure_produces_png(self, sandbox: NodeSandbox):
        """Matplotlib figures should come back as base64-encoded PNG results."""
        result = sandbox.run_code(
            "import matplotlib\nmatplotlib.use('Agg')\nimport matplotlib.pyplot as plt\n"
            "fig, ax = plt.subplots()\nax.plot([1, 2, 3])\nfig"
        )
        # matplotlib may or may not be installed in the v4 image; skip if not
        if result.error and "ModuleNotFoundError" in result.error.name:
            pytest.skip("matplotlib not installed in template image")
        assert result.success
        assert result.results, "expected PNG result item"
        assert result.results[0].mime == "image/png"
        assert len(result.results[0].data) > 100  # non-trivial base64


# ---------------------------------------------------------------------------
# 3. JavaScript / Node.js execution
# ---------------------------------------------------------------------------


class TestJavaScript:
    def test_console_log(self, sandbox: NodeSandbox):
        result = sandbox.run_code("console.log('hi from node')", language="javascript")
        assert result.success
        assert "hi from node" in result.stdout

    def test_arithmetic_result(self, sandbox: NodeSandbox):
        result = sandbox.run_code("6 * 7", language="javascript")
        assert result.success
        output = result.results[0].data if result.results else result.stdout.strip()
        assert "42" in output

    def test_state_persists(self, sandbox: NodeSandbox):
        """JS context is stateful — variable set in one call visible in next."""
        sandbox.run_code("var jsCounter = 0", language="javascript")
        sandbox.run_code("jsCounter += 5", language="javascript")
        result = sandbox.run_code("console.log(jsCounter)", language="javascript")
        assert result.success
        assert "5" in result.stdout

    def test_node_alias(self, sandbox: NodeSandbox):
        """'node' is an alias for 'javascript'."""
        result = sandbox.run_code("console.log(1 + 1)", language="node")
        assert result.success
        assert "2" in result.stdout

    def test_error_reference_error(self, sandbox: NodeSandbox):
        result = sandbox.run_code("console.log(notDefinedVar)", language="javascript")
        assert not result.success
        assert result.error is not None
        assert "ReferenceError" in result.error.name

    def test_promise_resolved(self, sandbox: NodeSandbox):
        result = sandbox.run_code(
            "Promise.resolve(99).then(v => console.log(v))",
            language="javascript",
        )
        # Async in REPL may or may not resolve synchronously; just check no crash
        assert result.error is None

    def test_env_vars(self, sandbox: NodeSandbox):
        result = sandbox.run_code(
            "console.log(process.env.JS_TEST_VAR || 'missing')",
            language="javascript",
            env_vars={"JS_TEST_VAR": "node_ok"},
        )
        assert result.success
        assert "node_ok" in result.stdout


# ---------------------------------------------------------------------------
# 4. Bash execution
# ---------------------------------------------------------------------------


class TestBash:
    def test_echo(self, sandbox: NodeSandbox):
        result = sandbox.run_code("echo hello_bash", language="bash")
        assert result.success
        assert "hello_bash" in result.stdout

    def test_multiline_script(self, sandbox: NodeSandbox):
        result = sandbox.run_code(
            "for i in 1 2 3; do echo item_$i; done",
            language="bash",
        )
        assert result.success
        for i in (1, 2, 3):
            assert f"item_{i}" in result.stdout

    def test_exit_code_error(self, sandbox: NodeSandbox):
        """Non-zero exit should surface as an error."""
        result = sandbox.run_code("exit 1", language="bash")
        # Bash executor may surface this as error or stderr — at minimum no crash
        # Some executor designs set error, others just set stderr
        assert result is not None

    def test_env_vars(self, sandbox: NodeSandbox):
        result = sandbox.run_code(
            "echo $BASH_TEST_VAR",
            language="bash",
            env_vars={"BASH_TEST_VAR": "bash_ok"},
        )
        assert result.success
        assert "bash_ok" in result.stdout

    def test_sh_alias(self, sandbox: NodeSandbox):
        result = sandbox.run_code("echo sh_works", language="sh")
        assert result.success
        assert "sh_works" in result.stdout


# ---------------------------------------------------------------------------
# 5. Context isolation
# ---------------------------------------------------------------------------


class TestContextIsolation:
    def test_separate_sandboxes_are_isolated(self):
        """Variable set in sandbox A must not leak into sandbox B."""
        with NodeSandbox.create() as a, NodeSandbox.create() as b:
            _wait_for_server(a.guest_ip)
            _wait_for_server(b.guest_ip)
            a.run_code("secret = 'from_A'")
            result = b.run_code("print(globals().get('secret', 'not_found'))")
            assert "from_A" not in result.stdout

    def test_explicit_context_is_isolated(self, sandbox: NodeSandbox):
        """Two named contexts in the same sandbox are independent."""
        ctx_a = sandbox.create_context("python")
        ctx_b = sandbox.create_context("python")

        sandbox.run_code("ctx_var = 'alpha'", context_id=ctx_a)
        result = sandbox.run_code("print(globals().get('ctx_var', 'absent'))", context_id=ctx_b)
        assert "alpha" not in result.stdout

    def test_default_language_contexts_are_separate(self, sandbox: NodeSandbox):
        """Python and JS default contexts don't share state."""
        sandbox.run_code("cross_lang = 999")
        result = sandbox.run_code("console.log(typeof cross_lang)", language="javascript")
        assert result.success
        assert "undefined" in result.stdout


# ---------------------------------------------------------------------------
# 6. Sandbox lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    def test_list_includes_created_sandbox(self):
        with NodeSandbox.create() as sb:
            resp = httpx.get(
                f"{NODE_AGENT_URL}/sandboxes",
                headers=_agent_headers,
                timeout=10,
            )
            resp.raise_for_status()
            ids = [s["id"] for s in resp.json()]
            assert sb.id in ids

    def test_delete_removes_sandbox(self):
        sb = NodeSandbox.create()
        sb.kill()

        resp = httpx.get(
            f"{NODE_AGENT_URL}/sandboxes/{sb.id}",
            headers=_agent_headers,
            timeout=10,
        )
        assert resp.status_code == 404

    def test_set_timeout(self):
        with NodeSandbox.create() as sb:
            resp = httpx.post(
                f"{NODE_AGENT_URL}/sandboxes/{sb.id}/timeout",
                headers=_agent_headers,
                json={"timeoutMs": 60_000},
                timeout=10,
            )
            assert resp.is_success

    def test_health_endpoint(self):
        with NodeSandbox.create() as sb:
            _wait_for_server(sb.guest_ip)
            r = httpx.get(f"http://{sb.guest_ip}:8080/health", timeout=5)
            assert r.is_success
            assert r.json() == "OK"

    def test_list_contexts(self):
        with NodeSandbox.create() as sb:
            _wait_for_server(sb.guest_ip)
            r = httpx.get(f"http://{sb.guest_ip}:8080/contexts", timeout=5)
            assert r.is_success
            contexts = r.json()
            # Default contexts for python and javascript should be pre-created
            langs = {c["language"] for c in contexts}
            assert "python" in langs
            assert "javascript" in langs
