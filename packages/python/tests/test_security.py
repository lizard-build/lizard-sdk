"""Shell-free make_dir, exit-code checks and URL-encoded ids, with the transport mocked."""
import httpx
import pytest

from lizard import LizardError, Sandbox

CONFIG = {"api_key": "liz_test", "api_url": "https://test.invalid"}


class _Calls(list):
    pass


@pytest.fixture
def execs(monkeypatch):
    calls = _Calls()
    calls.reply = {"stdout": "", "stderr": "", "exitCode": 0}

    def post(url, **kw):
        calls.append((url, kw["json"]))
        return httpx.Response(200, json=calls.reply)

    monkeypatch.setattr(httpx, "post", post)
    return calls


def test_make_dir_sends_argv(execs):
    path = "/tmp/$(id)/`id`/$HOME"
    Sandbox(sandbox_id="sb1", **CONFIG).fs.make_dir(path)
    url, body = execs[0]
    assert url == "https://test.invalid/api/sandboxes/sb1/exec"
    assert body["cmd"] == ["mkdir", "-p", "--", path]


def test_make_dir_raises_on_failure(execs):
    execs.reply = {"stdout": "", "stderr": "mkdir: Permission denied", "exitCode": 1}
    with pytest.raises(LizardError):
        Sandbox(sandbox_id="sb1", **CONFIG).fs.make_dir("/root/x")


def test_sandbox_id_is_url_encoded(execs):
    Sandbox(sandbox_id="../admin?x=1#", **CONFIG).process.exec_("true")
    assert execs[0][0] == "https://test.invalid/api/sandboxes/..%2Fadmin%3Fx%3D1%23/exec"
