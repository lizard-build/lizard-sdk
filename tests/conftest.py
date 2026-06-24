"""
Session-scoped sandbox fixtures shared by all test modules.

A single code-interpreter-v1 VM is created once per pytest session and
reused by both test_code_interpreter.py (uses `sandbox` fixture) and
test_e2b_parity.py (uses `sb` fixture). Running two simultaneous VMs in
the combined test run caused one to be evicted under memory pressure.

Both fixture names yield the SAME underlying sandbox object.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Callable

import httpx
import pytest

from lizard.code_interpreter.types import Execution, ExecutionError, ResultItem

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
    raise TimeoutError(f"{guest_ip}:8080 not ready after {timeout}s")


@pytest.fixture(scope="session")
def sandbox():
    """Single code-interpreter sandbox shared across the full test session."""
    sb = NodeSandbox.create(timeout_ms=3_600_000)  # 1-hour timeout
    _wait(sb.guest_ip)
    yield sb
    sb.kill()


@pytest.fixture(scope="session")
def sb(sandbox: NodeSandbox) -> NodeSandbox:
    """Alias for `sandbox` used by test_e2b_parity.py tests."""
    return sandbox
