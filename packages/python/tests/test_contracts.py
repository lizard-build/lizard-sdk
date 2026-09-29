"""Shared CLI/backend wire contracts. No live resources or payment calls."""
import inspect
import json
from pathlib import Path
from urllib.parse import urlparse, parse_qsl
import httpx
import pytest
from lizard import Lizard, Sandbox, Volume

CASES = json.loads((Path(__file__).parents[3] / "tests/contracts/platform.json").read_text())
CONFIG = {"api_key": "liz_contract_test", "api_url": "https://contract.invalid"}


def hydrate(value):
    if value == "__BYTES__":
        return bytes([0, 255, 31, 139])
    if isinstance(value, list):
        return [hydrate(v) for v in value]
    if isinstance(value, dict):
        return {k: hydrate(v) for k, v in value.items()}
    return value


def address(path):
    url = urlparse(path)
    return url.path, sorted(parse_qsl(url.query))


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
def test_contract(case, monkeypatch):
    calls = []

    def handler(request):
        want = case["requests"][len(calls)]
        calls.append(request)
        assert address(str(request.url)) == address(want["path"])
        assert request.method == want["method"]
        assert request.headers["X-API-Key"] == CONFIG["api_key"]
        if "body" in want:
            assert json.loads(request.content) == want.get("pyBody", want["body"])
        if "rawBody" in want:
            assert list(request.content) == want["rawBody"]
            assert request.headers["Content-Type"] == want["contentType"]
        return httpx.Response(want.get("status", 200),
            content=bytes(want["binaryResponse"]) if "binaryResponse" in want else want.get("rawResponse", want.get("stream", json.dumps(want["response"]))).encode(),
            headers={"Content-Type": "text/event-stream" if "stream" in want else "application/json"})

    original = httpx.Client.__init__
    def init(self, *a, **kw):
        kw["transport"] = httpx.MockTransport(handler)
        original(self, *a, **kw)
    monkeypatch.setattr(httpx.Client, "__init__", init)
    root = Lizard(**CONFIG)
    root.sandbox = Sandbox("sb1", **CONFIG)

    def execute():
        spec = case["py"]
        parts = spec["path"].split(".")
        target = {"Sandbox": Sandbox, "Volume": Volume}.get(parts[0], root)
        for part in (parts[1:-1] if parts[0] in ("Sandbox", "Volume") else parts[:-1]):
            target = getattr(target, part)
        kwargs = hydrate(spec.get("kwargs", {}))
        if parts[0] in ("Sandbox", "Volume"):
            kwargs.update(CONFIG)
        result = getattr(target, parts[-1])(*hydrate(spec["args"]), **kwargs)
        return list(result) if inspect.isgenerator(result) else result

    if case.get("error"):
        with pytest.raises(Exception, match=case["error"]):
            execute()
    else:
        result = execute()
        if case["name"] == "services.exec":
            assert result == {"stdout": "hi\n", "stderr": "oops\n", "exitCode": 2}
        if case["name"] == "services.logs":
            assert len(result) == 1
        if case["name"] == "metrics.all":
            assert len(result.network_rx) == 2
        if case["name"] == "domains.list":
            assert result[1].txt_value == "proof"
    assert len(calls) == len(case["requests"])
