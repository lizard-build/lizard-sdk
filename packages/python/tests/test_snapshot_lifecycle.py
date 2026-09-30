import pytest
from lizard import Sandbox, ConflictError, TimeoutError
from lizard.sandbox.sandbox import SandboxInfo
CONFIG = {"api_key": "liz_test", "api_url": "https://test.invalid"}

@pytest.mark.parametrize("status", ["failed", "paused", "suspended"])
def test_snapshot_wait_stops_for_unusable_state(monkeypatch, status):
    monkeypatch.setattr(Sandbox, "get_snapshot", lambda *a, **k: {"status": status, "error": "Cannot restore"})
    with pytest.raises(ConflictError, match="Cannot restore"):
        Sandbox.wait_for_snapshot("snap-1", **CONFIG)

def test_snapshot_wait_ready_and_timeout(monkeypatch):
    monkeypatch.setattr(Sandbox, "get_snapshot", lambda *a, **k: {"status": "ready", "readyCount": 5})
    assert Sandbox.wait_for_snapshot("snap-1", **CONFIG)["readyCount"] == 5
    monkeypatch.setattr(Sandbox, "get_snapshot", lambda *a, **k: {"status": "warming"})
    with pytest.raises(TimeoutError):
        Sandbox.wait_for_snapshot("snap-1", wait_timeout_ms=0, **CONFIG)

def test_sandbox_wait_reports_criu_error_and_timeout(monkeypatch):
    sandbox = Sandbox("sb-1", **CONFIG)
    monkeypatch.setattr(sandbox, "get_info", lambda: SandboxInfo("sb-1", "base", "", "", status="running", pause_error="Disconnect active clients"))
    with pytest.raises(ConflictError, match="Disconnect active clients"):
        sandbox.wait_for_status("paused")
    monkeypatch.setattr(sandbox, "get_info", lambda: SandboxInfo("sb-1", "base", "", "", status="resuming"))
    with pytest.raises(TimeoutError):
        sandbox.wait_for_status("running", wait_timeout_ms=0)


def test_snapshot_wait_requires_usable_capacity(monkeypatch):
    monkeypatch.setattr(Sandbox, "get_snapshot", lambda *a, **k: {"status": "ready", "readyCount": 0, "poolSize": 5})
    with pytest.raises(TimeoutError):
        Sandbox.wait_for_snapshot("snap-1", wait_timeout_ms=0, **CONFIG)
