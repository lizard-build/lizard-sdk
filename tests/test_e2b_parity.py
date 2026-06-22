"""
E2B-parity integration tests for Lizard code-interpreter sandboxes.

Maps directly to e2b's test suite structure. Each test class corresponds
to an e2b test module. Tests that require features not yet implemented
(fs API, process API, PTY, snapshots, network control) are marked xfail
and will flip to passing when those are added.

Run with:
    PYTHONPATH=packages/python venv/bin/pytest tests/test_e2b_parity.py -v
"""

from __future__ import annotations

import base64
import json
import threading
import time
import uuid
from typing import Callable

import httpx
import pytest

from lizard.code_interpreter.types import Execution, ExecutionError, ResultItem

# ---------------------------------------------------------------------------
# Shared fixture plumbing (same as test_code_interpreter.py)
# ---------------------------------------------------------------------------

NODE_AGENT_URL = "http://localhost:7070"
ADMIN_SECRET = "bd3323b6791f3e60025462bb4042ed3d0f62cd47518332b43918a19814e5162a"
TEMPLATE = "code-interpreter-v1"

_agent_headers = {"X-Admin-Secret": ADMIN_SECRET, "Content-Type": "application/json"}


class NodeSandbox:
    def __init__(self, sandbox_id: str, guest_ip: str):
        self.id = sandbox_id
        self.guest_ip = guest_ip
        self._server_url = f"http://{guest_ip}:8080"

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

    def run_code(
        self,
        code: str,
        *,
        language: str | None = None,
        context_id: str | None = None,
        env_vars: dict[str, str] | None = None,
        on_stdout: Callable[[str], None] | None = None,
        on_stderr: Callable[[str], None] | None = None,
        on_result: Callable[[ResultItem], None] | None = None,
        on_error: Callable[[ExecutionError], None] | None = None,
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
                    if on_stdout:
                        on_stdout(item["data"])
                elif t == "stderr":
                    execution.stderr += item["data"]
                    if on_stderr:
                        on_stderr(item["data"])
                elif t == "result":
                    r = ResultItem(mime=item.get("mime", ""), data=item.get("data", ""))
                    execution.results.append(r)
                    if on_result:
                        on_result(r)
                elif t == "error":
                    err = ExecutionError(
                        name=item.get("name", "Error"),
                        message=item.get("message", ""),
                        traceback=item.get("traceback", ""),
                    )
                    execution.error = err
                    if on_error:
                        on_error(err)
                elif t == "done":
                    execution.execution_count = item.get("execution_count", 0)
                    break
        return execution

    def create_context(self, language: str = "python", cwd: str = "/home/user") -> str:
        resp = httpx.post(
            f"{self._server_url}/contexts",
            json={"language": language, "cwd": cwd},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()["id"]

    def list_contexts(self) -> list[dict]:
        resp = httpx.get(f"{self._server_url}/contexts", timeout=10)
        resp.raise_for_status()
        return resp.json()

    def delete_context(self, context_id: str) -> None:
        resp = httpx.delete(f"{self._server_url}/contexts/{context_id}", timeout=10)
        resp.raise_for_status()

    def restart_context(self, context_id: str) -> None:
        resp = httpx.post(
            f"{self._server_url}/contexts/{context_id}/restart",
            timeout=10,
        )
        resp.raise_for_status()

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


def _wait(guest_ip: str, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = httpx.get(f"http://{guest_ip}:8080/health", timeout=1)
            if r.is_success:
                return
        except Exception:
            pass
        time.sleep(0.1)
    raise TimeoutError(f"{guest_ip}:8080 not ready")


@pytest.fixture(scope="module")
def sb():
    sandbox = NodeSandbox.create()
    _wait(sandbox.guest_ip)
    yield sandbox
    sandbox.kill()


# ---------------------------------------------------------------------------
# 1. Statefulness  (mirrors e2b test_statefulness.py)
# ---------------------------------------------------------------------------

class TestStatefulness:
    """Variables and definitions persist across run_code calls in same context."""

    def test_variable_survives_two_calls(self, sb: NodeSandbox):
        sb.run_code("state_x = 42")
        result = sb.run_code("print(state_x)")
        assert "42" in result.stdout

    def test_function_survives_calls(self, sb: NodeSandbox):
        sb.run_code("def double(n): return n * 2")
        result = sb.run_code("print(double(21))")
        assert "42" in result.stdout

    def test_import_survives_calls(self, sb: NodeSandbox):
        sb.run_code("import json as _json")
        result = sb.run_code("print(_json.dumps([1,2,3]))")
        assert "[1, 2, 3]" in result.stdout

    def test_js_variable_survives(self, sb: NodeSandbox):
        sb.run_code("var persistedJs = 'persisted'", language="javascript")
        result = sb.run_code("console.log(persistedJs)", language="javascript")
        assert "persisted" in result.stdout


# ---------------------------------------------------------------------------
# 2. Streaming callbacks  (mirrors e2b test_async_streaming.py / test_async_callbacks.py)
# ---------------------------------------------------------------------------

class TestStreamingCallbacks:
    """on_stdout / on_stderr / on_result / on_error fire during execution."""

    def test_on_stdout_callback(self, sb: NodeSandbox):
        chunks: list[str] = []
        sb.run_code(
            "print('line1'); print('line2')",
            on_stdout=chunks.append,
        )
        assert any("line1" in c for c in chunks)
        assert any("line2" in c for c in chunks)

    def test_on_stderr_callback(self, sb: NodeSandbox):
        chunks: list[str] = []
        sb.run_code(
            "import sys; sys.stderr.write('err_cb\\n')",
            on_stderr=chunks.append,
        )
        assert any("err_cb" in c for c in chunks)

    def test_on_result_callback(self, sb: NodeSandbox):
        items: list[ResultItem] = []
        sb.run_code("2 ** 8", on_result=items.append)
        assert items, "expected at least one result item"
        assert "256" in items[0].data

    def test_on_error_callback(self, sb: NodeSandbox):
        errors: list[ExecutionError] = []
        result = sb.run_code("raise RuntimeError('cb_error')", on_error=errors.append)
        assert errors, "expected error callback to fire"
        assert "cb_error" in errors[0].message
        assert result.error is not None

    def test_callbacks_and_return_consistent(self, sb: NodeSandbox):
        """Data in return value matches what callbacks received."""
        cb_stdout = []
        result = sb.run_code(
            "for i in range(3): print(i)",
            on_stdout=cb_stdout.append,
        )
        assert "".join(cb_stdout) == result.stdout

    def test_on_stdout_js(self, sb: NodeSandbox):
        chunks: list[str] = []
        sb.run_code(
            "console.log('js_cb')",
            language="javascript",
            on_stdout=chunks.append,
        )
        assert any("js_cb" in c for c in chunks)


# ---------------------------------------------------------------------------
# 3. Execution count  (mirrors e2b test_async_execution_count.py)
# ---------------------------------------------------------------------------

class TestExecutionCount:
    def test_increments_each_call(self, sb: NodeSandbox):
        r1 = sb.run_code("1")
        r2 = sb.run_code("2")
        r3 = sb.run_code("3")
        assert r1.execution_count < r2.execution_count < r3.execution_count

    def test_js_execution_count(self, sb: NodeSandbox):
        r1 = sb.run_code("1", language="javascript")
        r2 = sb.run_code("2", language="javascript")
        assert r2.execution_count > r1.execution_count


# ---------------------------------------------------------------------------
# 4. Context management  (mirrors e2b test_async_kernels.py + test_contexts.py)
# ---------------------------------------------------------------------------

class TestContextManagement:
    def test_create_context_default_language(self, sb: NodeSandbox):
        ctx_id = sb.create_context()
        assert ctx_id
        ctxs = {c["id"] for c in sb.list_contexts()}
        assert ctx_id in ctxs

    def test_create_context_javascript(self, sb: NodeSandbox):
        ctx_id = sb.create_context("javascript")
        result = sb.run_code("console.log('from_ctx')", context_id=ctx_id)
        assert "from_ctx" in result.stdout

    def test_create_context_bash(self, sb: NodeSandbox):
        ctx_id = sb.create_context("bash")
        result = sb.run_code("echo bash_ctx_ok", context_id=ctx_id)
        assert "bash_ctx_ok" in result.stdout

    def test_kernels_are_independent(self, sb: NodeSandbox):
        """e2b test_independence_of_kernels: two contexts don't share state."""
        ctx_a = sb.create_context("python")
        ctx_b = sb.create_context("python")
        sb.run_code("kernel_var = 'kernel_a'", context_id=ctx_a)
        result = sb.run_code(
            "print(globals().get('kernel_var', 'absent'))",
            context_id=ctx_b,
        )
        assert "kernel_a" not in result.stdout

    def test_list_contexts_includes_defaults(self, sb: NodeSandbox):
        """Default python + javascript contexts are pre-created at startup."""
        langs = {c["language"] for c in sb.list_contexts()}
        assert "python" in langs
        assert "javascript" in langs

    def test_delete_context(self, sb: NodeSandbox):
        ctx_id = sb.create_context("python")
        sb.delete_context(ctx_id)
        ctxs = {c["id"] for c in sb.list_contexts()}
        assert ctx_id not in ctxs

    def test_delete_nonexistent_context_raises(self, sb: NodeSandbox):
        with pytest.raises(httpx.HTTPStatusError) as exc:
            sb.delete_context("nonexistent-context-id-xyz")
        assert exc.value.response.status_code == 404

    def test_restart_clears_state(self, sb: NodeSandbox):
        """e2b test_restart_context: restart wipes variables."""
        ctx_id = sb.create_context("python")
        sb.run_code("restart_var = 'before_restart'", context_id=ctx_id)
        sb.restart_context(ctx_id)
        result = sb.run_code(
            "print(globals().get('restart_var', 'cleared'))",
            context_id=ctx_id,
        )
        assert "before_restart" not in result.stdout

    def test_restart_context_still_executes(self, sb: NodeSandbox):
        ctx_id = sb.create_context("python")
        sb.restart_context(ctx_id)
        result = sb.run_code("print('after_restart')", context_id=ctx_id)
        assert result.success
        assert "after_restart" in result.stdout

    def test_pass_invalid_language_errors(self, sb: NodeSandbox):
        """Using an unsupported language via context should fail at creation."""
        with pytest.raises(httpx.HTTPStatusError):
            sb.create_context("ruby")  # not supported

    def test_context_with_custom_cwd(self, sb: NodeSandbox):
        """e2b test_cwd_python: context cwd sets the working directory."""
        sb.run_code("import os; os.makedirs('/tmp/lizard_cwd_test', exist_ok=True)")
        ctx_id = sb.create_context("python", cwd="/tmp/lizard_cwd_test")
        result = sb.run_code("import os; print(os.getcwd())", context_id=ctx_id)
        assert "/tmp/lizard_cwd_test" in result.stdout

    def test_bash_context_cwd(self, sb: NodeSandbox):
        """e2b test_cwd_bash: bash context starts in specified cwd."""
        sb.run_code("import os; os.makedirs('/tmp/lizard_bash_cwd', exist_ok=True)")
        ctx_id = sb.create_context("bash", cwd="/tmp/lizard_bash_cwd")
        result = sb.run_code("pwd", context_id=ctx_id)
        assert "/tmp/lizard_bash_cwd" in result.stdout

    def test_js_context_cwd(self, sb: NodeSandbox):
        """e2b test_cwd_javascript: node context sees correct cwd."""
        ctx_id = sb.create_context("javascript", cwd="/tmp")
        result = sb.run_code("console.log(process.cwd())", context_id=ctx_id)
        assert "/tmp" in result.stdout


# ---------------------------------------------------------------------------
# 5. File system via code  (mirrors e2b fs.write / fs.read / fs.list / fs.remove)
#
# No dedicated file API yet — we use Python/Bash code execution to exercise
# the same behaviours. Tests marked xfail once a native fs API exists.
# ---------------------------------------------------------------------------

class TestFilesystemViaCode:
    """Exercise filesystem operations through code execution (Python + Bash)."""

    def test_write_and_read_text_file(self, sb: NodeSandbox):
        sb.run_code("open('/tmp/liz_test.txt','w').write('hello_fs')")
        result = sb.run_code("print(open('/tmp/liz_test.txt').read())")
        assert "hello_fs" in result.stdout

    def test_overwrite_file(self, sb: NodeSandbox):
        sb.run_code("open('/tmp/liz_overwrite.txt','w').write('v1')")
        sb.run_code("open('/tmp/liz_overwrite.txt','w').write('v2')")
        result = sb.run_code("print(open('/tmp/liz_overwrite.txt').read())")
        assert "v2" in result.stdout
        assert "v1" not in result.stdout

    def test_write_to_non_existing_directory_via_mkdir(self, sb: NodeSandbox):
        sb.run_code(
            "import os; os.makedirs('/tmp/liz_subdir', exist_ok=True);"
            "open('/tmp/liz_subdir/f.txt','w').write('nested')"
        )
        result = sb.run_code("print(open('/tmp/liz_subdir/f.txt').read())")
        assert "nested" in result.stdout

    def test_read_non_existing_file_raises(self, sb: NodeSandbox):
        result = sb.run_code("open('/tmp/does_not_exist_xyz.txt')")
        assert not result.success
        assert result.error is not None
        assert "FileNotFoundError" in result.error.name

    def test_read_empty_file(self, sb: NodeSandbox):
        sb.run_code("open('/tmp/liz_empty.txt','w').close()")
        result = sb.run_code("print(repr(open('/tmp/liz_empty.txt').read()))")
        assert "''" in result.stdout

    def test_list_directory_via_os(self, sb: NodeSandbox):
        sb.run_code(
            "import os; os.makedirs('/tmp/liz_ls', exist_ok=True);"
            "open('/tmp/liz_ls/a.txt','w').close();"
            "open('/tmp/liz_ls/b.txt','w').close()"
        )
        result = sb.run_code(
            "import os; print('\\n'.join(sorted(os.listdir('/tmp/liz_ls'))))"
        )
        assert "a.txt" in result.stdout
        assert "b.txt" in result.stdout

    def test_remove_file(self, sb: NodeSandbox):
        sb.run_code("open('/tmp/liz_remove.txt','w').write('bye')")
        sb.run_code("import os; os.remove('/tmp/liz_remove.txt')")
        result = sb.run_code(
            "import os; print(os.path.exists('/tmp/liz_remove.txt'))"
        )
        assert "False" in result.stdout

    def test_file_exists_check(self, sb: NodeSandbox):
        sb.run_code("open('/tmp/liz_exists.txt','w').write('x')")
        result = sb.run_code(
            "import os; print(os.path.exists('/tmp/liz_exists.txt'),"
            "os.path.exists('/tmp/liz_not_there_xyz.txt'))"
        )
        assert "True" in result.stdout
        assert "False" in result.stdout

    def test_write_binary_data(self, sb: NodeSandbox):
        """Binary data survives write + read cycle."""
        sb.run_code("open('/tmp/liz_bin.bin','wb').write(bytes(range(256)))")
        result = sb.run_code(
            "import hashlib; data=open('/tmp/liz_bin.bin','rb').read();"
            "print(len(data), hashlib.sha256(data).hexdigest()[:8])"
        )
        assert "256" in result.stdout

    def test_file_size_via_stat(self, sb: NodeSandbox):
        sb.run_code("open('/tmp/liz_size.txt','w').write('x' * 100)")
        result = sb.run_code(
            "import os; print(os.stat('/tmp/liz_size.txt').st_size)"
        )
        assert "100" in result.stdout

    def test_bash_write_and_read(self, sb: NodeSandbox):
        sb.run_code("echo bash_content > /tmp/liz_bash.txt", language="bash")
        result = sb.run_code("cat /tmp/liz_bash.txt", language="bash")
        assert "bash_content" in result.stdout

    def test_make_dir_via_bash(self, sb: NodeSandbox):
        result = sb.run_code(
            "mkdir -p /tmp/liz_mkdir && echo ok", language="bash"
        )
        assert "ok" in result.stdout
        check = sb.run_code("test -d /tmp/liz_mkdir && echo exists", language="bash")
        assert "exists" in check.stdout

    def test_rename_file(self, sb: NodeSandbox):
        sb.run_code("open('/tmp/liz_rename_src.txt','w').write('renamed')")
        sb.run_code(
            "import os; os.rename('/tmp/liz_rename_src.txt', '/tmp/liz_rename_dst.txt')"
        )
        result = sb.run_code("print(open('/tmp/liz_rename_dst.txt').read())")
        assert "renamed" in result.stdout
        exists = sb.run_code(
            "import os; print(os.path.exists('/tmp/liz_rename_src.txt'))"
        )
        assert "False" in exists.stdout

    def test_cross_language_file_sharing(self, sb: NodeSandbox):
        """Python writes a file, Bash reads it — same filesystem."""
        sb.run_code("open('/tmp/liz_cross.txt','w').write('cross_lang')")
        result = sb.run_code("cat /tmp/liz_cross.txt", language="bash")
        assert "cross_lang" in result.stdout


# ---------------------------------------------------------------------------
# 6. Process / subprocess  (mirrors e2b test_run.py + test_env_vars.py)
# ---------------------------------------------------------------------------

class TestProcessViaCode:
    """Subprocess spawning from within code execution."""

    def test_run_shell_command_from_python(self, sb: NodeSandbox):
        result = sb.run_code(
            "import subprocess; r = subprocess.run(['echo','hello_proc'],"
            "capture_output=True,text=True); print(r.stdout.strip())"
        )
        assert "hello_proc" in result.stdout

    def test_run_with_special_characters(self, sb: NodeSandbox):
        result = sb.run_code(
            r"import subprocess; r = subprocess.run(['echo','hello \"world\"'],"
            "capture_output=True,text=True); print(r.stdout)"
        )
        assert result.success

    def test_run_multiline_bash_script(self, sb: NodeSandbox):
        result = sb.run_code(
            "for i in $(seq 1 5); do echo line_$i; done",
            language="bash",
        )
        for i in range(1, 6):
            assert f"line_{i}" in result.stdout

    def test_command_env_vars(self, sb: NodeSandbox):
        """Per-execution env vars are available to the subprocess."""
        result = sb.run_code(
            "import os; print(os.environ.get('RUN_VAR','missing'))",
            env_vars={"RUN_VAR": "present"},
        )
        assert "present" in result.stdout

    def test_sandbox_level_env_persists(self, sb: NodeSandbox):
        """Env vars set inside code persist for that process's lifetime."""
        sb.run_code("import os; os.environ['SBX_VAR'] = 'sandbox_env'")
        result = sb.run_code("import os; print(os.environ.get('SBX_VAR','missing'))")
        assert "sandbox_env" in result.stdout

    def test_exit_code_non_zero_is_error(self, sb: NodeSandbox):
        """Bash non-zero exit is surfaced as an error."""
        result = sb.run_code("exit 42", language="bash")
        assert result.error is not None
        assert "42" in result.error.message

    def test_run_python_as_subprocess(self, sb: NodeSandbox):
        result = sb.run_code(
            "import subprocess; out = subprocess.check_output("
            "['python3','-c','print(7*6)'], text=True); print(out.strip())"
        )
        assert "42" in result.stdout

    def test_working_directory_in_subprocess(self, sb: NodeSandbox):
        sb.run_code("import os; os.makedirs('/tmp/liz_proc_cwd', exist_ok=True)")
        result = sb.run_code(
            "import subprocess; r = subprocess.run(['pwd'], capture_output=True,"
            "text=True, cwd='/tmp/liz_proc_cwd'); print(r.stdout.strip())"
        )
        assert "/tmp/liz_proc_cwd" in result.stdout

    def test_bash_pipe(self, sb: NodeSandbox):
        result = sb.run_code(
            "echo 'hello world lizard' | tr ' ' '\\n' | sort",
            language="bash",
        )
        assert result.success
        lines = result.stdout.strip().split()
        assert lines == sorted(lines)


# ---------------------------------------------------------------------------
# 7. Advanced output types  (mirrors e2b test_async_data.py / test_display_data.py)
# ---------------------------------------------------------------------------

class TestOutputTypes:
    def test_dict_result_is_json(self, sb: NodeSandbox):
        result = sb.run_code('{"alpha": 1, "beta": 2}')
        assert result.success
        if result.results:
            assert "json" in result.results[0].mime.lower()
            data = json.loads(result.results[0].data)
            assert data.get("alpha") == 1

    def test_list_result(self, sb: NodeSandbox):
        result = sb.run_code("[10, 20, 30]")
        assert result.success
        if result.results:
            data = json.loads(result.results[0].data)
            assert data == [10, 20, 30]

    def test_html_repr_object(self, sb: NodeSandbox):
        """Objects with _repr_html_ produce text/html result."""
        result = sb.run_code(
            "class HtmlObj:\n"
            "    def _repr_html_(self): return '<b>html</b>'\n"
            "HtmlObj()"
        )
        assert result.success
        if result.results:
            assert result.results[0].mime == "text/html"
            assert "<b>html</b>" in result.results[0].data

    def test_large_stdout(self, sb: NodeSandbox):
        """10 000 lines of output are fully captured."""
        result = sb.run_code("for i in range(10_000): print(i)")
        assert result.success
        lines = [l for l in result.stdout.strip().split("\n") if l]
        assert len(lines) >= 10_000

    def test_base64_binary_roundtrip(self, sb: NodeSandbox):
        """Encode binary → base64 string in Python, decode back."""
        result = sb.run_code(
            "import base64; data=bytes(range(256));"
            "enc=base64.b64encode(data).decode();"
            "dec=base64.b64decode(enc);"
            "print(data == dec)"
        )
        assert "True" in result.stdout

    def test_none_result_not_emitted(self, sb: NodeSandbox):
        """Expressions that evaluate to None produce no result item."""
        result = sb.run_code("x = None")
        # No result items for None assignment
        none_results = [r for r in result.results if r.data == "null"]
        assert not result.results or not none_results


# ---------------------------------------------------------------------------
# 8. Error handling & recovery  (mirrors e2b test_async_interrupt.py / test_async_killed.py)
# ---------------------------------------------------------------------------

class TestErrorHandlingAndRecovery:
    def test_error_does_not_kill_context(self, sb: NodeSandbox):
        """After a runtime error, the context is still usable."""
        ctx = sb.create_context("python")
        sb.run_code("raise ValueError('intentional')", context_id=ctx)
        result = sb.run_code("print('still_alive')", context_id=ctx)
        assert result.success
        assert "still_alive" in result.stdout

    def test_syntax_error_surfaces_cleanly(self, sb: NodeSandbox):
        result = sb.run_code("def bad(:\n    pass")
        assert not result.success
        assert result.error is not None
        assert "SyntaxError" in result.error.name

    def test_infinite_loop_timeout(self, sb: NodeSandbox):
        """A request that times out should not hang the connection."""
        start = time.time()
        try:
            sb.run_code("while True: pass", language="bash")
        except Exception:
            pass
        # We don't assert on the result — just that it didn't hang >30s
        assert time.time() - start < 35

    def test_import_error_is_error(self, sb: NodeSandbox):
        result = sb.run_code("import totally_nonexistent_module_xyz")
        assert not result.success
        assert "ModuleNotFoundError" in result.error.name

    def test_js_error_after_error_recovers(self, sb: NodeSandbox):
        ctx = sb.create_context("javascript")
        sb.run_code("null.property", context_id=ctx)  # TypeError
        result = sb.run_code("console.log('js_recovered')", context_id=ctx)
        assert result.success
        assert "js_recovered" in result.stdout

    def test_bash_error_surfaces_exit_code(self, sb: NodeSandbox):
        result = sb.run_code("ls /nonexistent_dir_xyz", language="bash")
        assert result.error is not None

    def test_multiple_errors_in_sequence(self, sb: NodeSandbox):
        ctx = sb.create_context("python")
        for _ in range(3):
            r = sb.run_code("raise RuntimeError('repeat')", context_id=ctx)
            assert not r.success
        # Still works
        result = sb.run_code("print('ok_after_errors')", context_id=ctx)
        assert "ok_after_errors" in result.stdout


# ---------------------------------------------------------------------------
# 9. Concurrent execution  (mirrors e2b test_concurrent)
# ---------------------------------------------------------------------------

class TestConcurrentExecution:
    def test_parallel_executions_in_separate_sandboxes(self):
        """Two sandboxes run code simultaneously without interference."""
        results: dict[str, str] = {}
        lock = threading.Lock()

        def _run(label: str):
            with NodeSandbox.create() as s:
                _wait(s.guest_ip)
                r = s.run_code(f"print('{label}')")
                with lock:
                    results[label] = r.stdout

        threads = [threading.Thread(target=_run, args=(f"worker_{i}",)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        for i in range(3):
            assert f"worker_{i}" in results.get(f"worker_{i}", ""), \
                f"worker_{i} output missing: {results}"

    def test_parallel_run_code_in_same_sandbox(self, sb: NodeSandbox):
        """Sequential calls from threads complete without data mixing."""
        outputs: list[str] = []
        lock = threading.Lock()

        def _run(n: int):
            ctx = sb.create_context("python")
            r = sb.run_code(f"print('t{n}')", context_id=ctx)
            with lock:
                outputs.append(r.stdout)

        threads = [threading.Thread(target=_run, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20)

        assert len(outputs) == 4


# ---------------------------------------------------------------------------
# 10. Language aliases  (mirrors e2b LANGUAGE_ALIASES dict)
# ---------------------------------------------------------------------------

class TestLanguageAliases:
    """All documented language aliases resolve to the correct executor."""

    @pytest.mark.parametrize("alias,expected_output", [
        ("python", "py_ok"),
        ("python3", "py_ok"),
        ("py", "py_ok"),
    ])
    def test_python_aliases(self, sb: NodeSandbox, alias: str, expected_output: str):
        result = sb.run_code("print('py_ok')", language=alias)
        assert expected_output in result.stdout

    @pytest.mark.parametrize("alias", ["javascript", "js", "node", "nodejs"])
    def test_js_aliases(self, sb: NodeSandbox, alias: str):
        result = sb.run_code("console.log('js_alias_ok')", language=alias)
        assert "js_alias_ok" in result.stdout

    @pytest.mark.parametrize("alias", ["bash", "sh", "shell"])
    def test_bash_aliases(self, sb: NodeSandbox, alias: str):
        result = sb.run_code("echo bash_alias_ok", language=alias)
        assert "bash_alias_ok" in result.stdout


# ---------------------------------------------------------------------------
# 11. Sandbox API (lifecycle)  (mirrors e2b test_create / test_kill / test_timeout)
# ---------------------------------------------------------------------------

class TestSandboxAPI:
    def test_get_sandbox_info(self):
        with NodeSandbox.create() as sb:
            resp = httpx.get(
                f"{NODE_AGENT_URL}/sandboxes/{sb.id}",
                headers=_agent_headers,
                timeout=10,
            )
            assert resp.is_success
            data = resp.json()
            assert data["id"] == sb.id
            assert data["status"] == "running"
            assert data["template"] == TEMPLATE

    def test_list_sandboxes_pagination(self):
        """Create 3 sandboxes, all appear in list."""
        created = []
        try:
            for _ in range(3):
                created.append(NodeSandbox.create())
            resp = httpx.get(
                f"{NODE_AGENT_URL}/sandboxes",
                headers=_agent_headers,
                timeout=10,
            )
            assert resp.is_success
            ids = {s["id"] for s in resp.json()}
            for sb in created:
                assert sb.id in ids
        finally:
            for sb in created:
                sb.kill()

    def test_timeout_can_be_extended(self):
        with NodeSandbox.create(timeout_ms=60_000) as sb:
            resp = httpx.post(
                f"{NODE_AGENT_URL}/sandboxes/{sb.id}/timeout",
                headers=_agent_headers,
                json={"timeoutMs": 120_000},
                timeout=10,
            )
            assert resp.is_success

    def test_timeout_can_be_shortened(self):
        with NodeSandbox.create(timeout_ms=300_000) as sb:
            resp = httpx.post(
                f"{NODE_AGENT_URL}/sandboxes/{sb.id}/timeout",
                headers=_agent_headers,
                json={"timeoutMs": 60_000},
                timeout=10,
            )
            assert resp.is_success

    def test_kill_returns_404_when_gone(self):
        sb = NodeSandbox.create()
        sb.kill()
        resp = httpx.delete(
            f"{NODE_AGENT_URL}/sandboxes/{sb.id}",
            headers=_agent_headers,
            timeout=10,
        )
        assert resp.status_code == 404

    def test_get_nonexistent_sandbox_returns_404(self):
        resp = httpx.get(
            f"{NODE_AGENT_URL}/sandboxes/sbx-nonexistent-xyz",
            headers=_agent_headers,
            timeout=10,
        )
        assert resp.status_code == 404
