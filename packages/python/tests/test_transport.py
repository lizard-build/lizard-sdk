import json
from pathlib import Path
import httpx
import pytest
from lizard import Lizard, LizardCLI, Sandbox
from lizard.config import ConnectionConfig
from lizard.platform.client import PlatformClient
from lizard.platform.services import ServicesAPI

CONFIG = {"api_key": "liz_test", "api_url": "https://test.invalid"}
FAKE_CLI = str(Path(__file__).parents[3] / "tests/fixtures/fake-cli.cjs")


def client_for(handler):
    client = PlatformClient(ConnectionConfig(**CONFIG))
    client._http.close()
    client._http = httpx.Client(base_url=CONFIG["api_url"], transport=httpx.MockTransport(handler))
    return client


def test_sse_multiline_crlf_unicode():
    client = client_for(lambda _: httpx.Response(200, content=': ping\r\nid: 7\r\nevent: stdout\r\ndata: привет\r\ndata: world\r\n\r\nevent: exit\r\ndata:{"exitCode":0}\r\n\r\n'.encode()))
    assert list(client.events("/stream")) == [
        {"event": "stdout", "data": "привет\nworld", "id": "7"},
        {"event": "exit", "data": '{"exitCode":0}', "id": "7"},
    ]


def test_truncated_exec_fails():
    client = client_for(lambda _: httpx.Response(200, text='data: {"stream":"stdout","line":"partial"}\n\n'))
    with pytest.raises(Exception, match="without exit status"):
        ServicesAPI(client).exec_("s1", "echo hi")


def test_stream_error_propagates():
    client = client_for(lambda _: httpx.Response(200, text='event: error\ndata: command failed\n\n'))
    with pytest.raises(Exception, match="command failed"):
        ServicesAPI(client).exec_("s1", "hi")


@pytest.mark.parametrize("method", ["post", "patch", "put", "delete"])
def test_empty_success(method):
    client = client_for(lambda _: httpx.Response(204))
    assert getattr(client, method)("/resource", {}) is None


def test_no_mutation_retry():
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(409, json={"error": "revision mismatch"})
    with pytest.raises(Exception, match="revision mismatch"):
        client_for(handler).post("/apply", {})
    assert len(calls) == 1


def test_zero_lifetime(monkeypatch):
    def post(url, **kw):
        assert kw["json"]["timeoutMs"] == 0
        return httpx.Response(200, json={"sandboxId": "s1"})
    monkeypatch.setattr(httpx, "post", post)
    Sandbox.create("base", project_id="p1", timeout_ms=0, **CONFIG)


def test_reject_lossy_binary_write(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **kw: pytest.fail("must not send"))
    with pytest.raises(UnicodeDecodeError):
        Sandbox("s", **CONFIG).fs.write("/tmp/data", bytes([255]))


def test_secret_project_guard():
    client = client_for(lambda _: httpx.Response(200, json={"name": "api", "projectId": "other"}))
    from lizard.platform.secrets import SecretsAPI
    with pytest.raises(ValueError, match="does not belong"):
        SecretsAPI(client).set("p1", {"K": "V"}, service_id="s")


def test_cli_literal_args_and_stdin():
    args = ["run", "--", "printf", "$(false); echo bad", "two words"]
    result = LizardCLI(executable=FAKE_CLI).run(args, stdin="KEY=value\n")
    assert result.code == 0
    assert result.events == [{"args": ["--json", *args], "input": "KEY=value\n"}]


def test_cli_error_status():
    assert LizardCLI(executable=FAKE_CLI).run(["fail"]).code == 3


def test_x402_cli_args():
    result = Lizard(**CONFIG).billing.pay_x402(2000, max_total_cents=2100, request_id="request-1", executable=FAKE_CLI)
    assert result == {"args": ["--json", "credits", "topup", "20.00", "--method", "x402", "--max-total", "21.00", "--yes", "--request-id", "request-1"], "input": ""}


def test_failed_build_is_not_old_running_service():
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"status": "failed"})
    from lizard.platform.services import DeployHandle
    with pytest.raises(Exception, match="Deploy failed"):
        DeployHandle(client_for(handler), "s1", "b1").wait()
    assert len(calls) == 1


def test_wait_does_not_accept_old_service():
    from lizard.platform.services import DeployHandle
    client = client_for(lambda r: httpx.Response(200, json={"status": "building"} if r.url.path.endswith("b1") else {"status": "running", "deployStatus": "idle"}))
    with pytest.raises(Exception, match="did not complete"):
        DeployHandle(client, "s1", "b1").wait(timeout_ms=5, poll_ms=1)


def test_project_cache_is_per_credential(monkeypatch):
    from lizard.project import resolve_project_id
    def get(url, **kwargs):
        key = kwargs["headers"]["X-API-Key"]
        return httpx.Response(200, json=[{"id": f"p_{key}", "name": "shared"}])
    monkeypatch.setattr(httpx, "get", get)
    assert resolve_project_id("shared", ConnectionConfig(api_key="first", api_url="https://cache.invalid")) == "p_first"
    assert resolve_project_id("shared", ConnectionConfig(api_key="second", api_url="https://cache.invalid")) == "p_second"


def test_ambiguous_project_rejected(monkeypatch):
    from lizard.project import resolve_project_id
    monkeypatch.setattr(httpx, "get", lambda *a, **kw: httpx.Response(200, json=[{"id": "p1", "name": "shared"}, {"id": "p2", "name": "shared"}]))
    with pytest.raises(Exception, match="ambiguous"):
        resolve_project_id("shared", ConnectionConfig(api_key="ambiguous", api_url="https://ambiguous.invalid"))


def test_config_side_effect_failure_is_not_success():
    from lizard import ConfigApplyError
    from lizard.platform.projects import ProjectsAPI
    response = {"revision": 8, "services": [], "addons": [], "sideEffectFailures": [{"action": "restart", "error": "unavailable"}]}
    with pytest.raises(ConfigApplyError) as exc:
        ProjectsAPI(client_for(lambda _: httpx.Response(200, json=response))).apply("p1", {})
    assert exc.value.result == response
