"""The Firecracker sandbox contract: pid events, binary writes, port tokens, fork,
file/process metadata and the exec-based code runner. No network."""
import base64
import contextlib
import json
from pathlib import Path

import httpx
import pytest

from lizard import CodeSandbox, ConflictError, LizardError, Sandbox
from lizard.code_interpreter._runner import SOURCE
from lizard.platform.client import PlatformClient

CONFIG = {"api_key": "liz_test", "api_url": "https://test.invalid"}


def sse(*events: str) -> str:
    return "".join(e + "\n\n" for e in events)


def fake_stream(monkeypatch, text: str, sent: list):
    @contextlib.contextmanager
    def stream(method, url, **kw):
        sent.append(kw["json"])
        yield httpx.Response(200, text=text)
    monkeypatch.setattr(httpx, "stream", stream)


def test_on_pid_asks_for_and_receives_the_pid(monkeypatch):
    sent = []
    fake_stream(monkeypatch, sse(": operation x", 'data: {"pid":1024}', 'data: {"stream":"stdout","line":"a"}',
                                 'event: exit\ndata: {"exitCode":4}'), sent)
    pids = []
    r = Sandbox("s", **CONFIG).process.exec_("echo a; exit 4", on_pid=pids.append)
    assert sent[0]["pidEvent"] is True
    assert pids == [1024]
    assert (r.stdout, r.exit_code) == ("a", 4)


def test_no_pid_event_without_on_pid(monkeypatch):
    sent = []
    fake_stream(monkeypatch, sse('data: {"stream":"stdout","line":"a"}', 'event: exit\ndata: {"exitCode":0}'), sent)
    Sandbox("s", **CONFIG).process.exec_("echo a", on_stdout=lambda _l: None)
    assert "pidEvent" not in sent[0]


def test_get_host_keeps_the_access_token(monkeypatch):
    answer = {"hostname": "s-3000.sandbox.eu.onlizard.com", "url": "https://s-3000.sandbox.eu.onlizard.com/?lizard_token=tok",
              "port": 3000, "accessToken": "tok"}
    monkeypatch.setattr(httpx, "post", lambda url, **kw: httpx.Response(200, json=answer))
    sb = Sandbox("s", **CONFIG)
    assert sb.get_host(3000) == answer["hostname"]
    assert sb.access_token == "tok"
    exposed = sb.expose_port(3000)
    assert (exposed.hostname, exposed.url, exposed.port, exposed.access_token) == (answer["hostname"], answer["url"], 3000, "tok")


def test_get_host_raises_api_errors(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda url, **kw: httpx.Response(409, json={"error": "crashed"}))
    with pytest.raises(ConflictError):
        Sandbox("s", **CONFIG).get_host(3000)


def mock_platform(sb, handler):
    pc = PlatformClient(sb._config)
    pc._http.close()
    pc._http = httpx.Client(base_url=CONFIG["api_url"], transport=httpx.MockTransport(handler))
    sb._pc = pc


def test_fork_returns_sandboxes_of_the_same_class():
    sb = CodeSandbox("s", **CONFIG)
    seen = []
    mock_platform(sb, lambda req: seen.append(json.loads(req.content)) or httpx.Response(201, json=[
        {"sandbox": {"sandboxId": "f1", "status": "running", "runtime": "firecracker"}},
        {"error": "Sandbox limit reached"},
    ]))
    forks = sb.fork(count=2)
    assert seen == [{"count": 2, "timeoutMs": 0}]
    assert isinstance(forks[0].sandbox, CodeSandbox) and forks[0].sandbox.sandbox_id == "f1"
    assert forks[0].ok and forks[0].info.runtime == "firecracker"
    assert forks[1].sandbox is None and forks[1].error == "Sandbox limit reached" and not forks[1].ok


def test_fork_volume_conflict():
    sb = Sandbox("s", **CONFIG)
    mock_platform(sb, lambda req: httpx.Response(409, json={"error": "A sandbox with a volume attached cannot be forked"}))
    with pytest.raises(ConflictError):
        sb.fork()


def test_platform_client_is_reused_and_closed():
    sb = Sandbox("s", **CONFIG)
    pc = sb._platform()
    assert sb._platform() is pc
    sb.close()
    assert pc._http.is_closed and sb._pc is None


def test_file_info_reads_mode_and_mod_time(monkeypatch):
    entry = {"type": "file", "name": "a", "path": "/tmp/a", "size": 3, "modTime": 1700000000000,
             "modifiedAt": 1700000000000, "mode": 420, "permissions": "-rw-r--r--", "owner": "user", "group": "user"}
    monkeypatch.setattr(httpx, "get", lambda url, **kw: httpx.Response(200, json=[entry] if url.endswith("/list") else entry))
    fs = Sandbox("s", **CONFIG).fs
    for info in (fs.list("/tmp")[0], fs.stat("/tmp/a")):
        assert (info.mode, info.mod_time, info.permissions, info.owner, info.group) == (420, 1700000000000, "-rw-r--r--", "user", "user")


def test_process_info_shape(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda url, **kw: httpx.Response(200, json=[
        {"pid": 7, "cmd": ["/bin/sh", "-c", "sleep 9"], "command": "/bin/sh -c sleep 9", "cwd": "/root", "tag": None}]))
    [p] = Sandbox("s", **CONFIG).process.list()
    assert (p.pid, p.cmd, p.command, p.cwd, p.started_at) == (7, ["/bin/sh", "-c", "sleep 9"], "/bin/sh -c sleep 9", "/root", 0)


def test_remove_and_watcher_close_use_the_sdk_timeout(monkeypatch):
    seen = []
    monkeypatch.setattr(httpx, "request", lambda method, url, **kw: seen.append(kw.get("timeout")) or httpx.Response(200, json={}))
    sb = Sandbox("s", **CONFIG)
    sb.fs.remove("/tmp/a")
    from lizard.sandbox.fs import Watcher
    Watcher("s", sb._config, "w1").close()
    assert seen == [60, 60]


def line(obj) -> str:
    return "data: " + json.dumps({"stream": "stdout", "line": json.dumps(obj)})


def test_run_code_through_exec(monkeypatch):
    result = json.dumps({"type": "result", "mime": "image/png", "data": "A" * 50})
    parts = [result[:20], result[20:40], result[40:]]
    sent = []
    fake_stream(monkeypatch, sse(
        line({"type": "stdout", "data": "hi\n"}),
        line({"type": "stderr", "data": "warn\n"}),
        *[line({"type": "part", "data": p, "end": i == len(parts) - 1}) for i, p in enumerate(parts)],
        line({"type": "error", "name": "ZeroDivisionError", "message": "division by zero", "traceback": "tb"}),
        line({"type": "done", "execution_count": 3}),
        'event: exit\ndata: {"exitCode":0}',
    ), sent)
    out = []
    run = CodeSandbox("c1", **CONFIG).run_code("1/0", envs={"A": "1"}, on_stdout=out.append)
    cmd = sent[0]["cmd"]
    assert cmd[:3] == ["python3", "-c", SOURCE]
    assert json.loads(base64.b64decode(cmd[3])) == {"action": "run", "code": "1/0", "envs": {"A": "1"}, "timeout": 60, "language": "python"}
    assert (run.stdout, run.stderr, out) == ("hi\n", "warn\n", ["hi\n"])
    assert [(r.mime, r.data) for r in run.results] == [("image/png", "A" * 50)]
    assert run.error.name == "ZeroDivisionError" and run.execution_count == 3


def test_run_code_fails_loudly_without_python(monkeypatch):
    fake_stream(monkeypatch, sse('data: {"stream":"stderr","line":"sh: python3: not found"}', 'event: exit\ndata: {"exitCode":127}'), [])
    with pytest.raises(LizardError, match="python3"):
        CodeSandbox("c1", **CONFIG).run_code("1")


def test_runner_matches_the_js_copy():
    ts = (Path(__file__).parents[2] / "js/src/code-interpreter/runner.ts").read_text()
    assert ts[ts.index("String.raw`") + len("String.raw`"):ts.rindex("`")] == SOURCE
