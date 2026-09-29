from __future__ import annotations
import json
from typing import Any, Iterator
from urllib.parse import quote, urlencode
import httpx
from ..config import ConnectionConfig
from ..errors import ConfigApplyError, handle_api_error


def segment(value: str) -> str:
    return quote(value, safe="")


def query(path: str, **values) -> str:
    values = {k: str(v).lower() if isinstance(v, bool) else v for k, v in values.items() if v is not None}
    return path + ("?" + urlencode(values) if values else "")


class PlatformClient:
    """HTTP transport. Calls never retry mutations or payments."""

    def __init__(self, config: ConnectionConfig) -> None:
        self._config = config
        self._http = httpx.Client(base_url=config.api_url, headers=config.headers, timeout=120)

    def _check(self, res: httpx.Response) -> None:
        if not res.is_success:
            res.read()
            # The raw body: handle_api_error pulls both `error` and `code` out of it.
            handle_api_error(res.status_code, res.text)

    def _json(self, res):
        self._check(res)
        return res.json() if res.status_code != 204 and res.content else None

    def get(self, path: str) -> Any:
        return self._json(self._http.get(path))

    def post(self, path: str, body: Any = None) -> Any:
        return self._json(self._http.post(path, content=json.dumps(body) if body is not None else None))

    def put(self, path: str, body: Any) -> Any:
        return self._json(self._http.put(path, json=body))

    def patch(self, path: str, body: Any) -> Any:
        return self._json(self._http.patch(path, content=json.dumps(body)))

    def delete(self, path: str, body: Any = None) -> Any:
        if body is None:
            return self._json(self._http.delete(path))
        return self._json(self._http.request("DELETE", path, json=body))

    def apply_config(self, project_id: str, body: Any) -> Any:
        result = self.post(f"/api/projects/{project_id}/config:apply", body)
        if result and result.get("sideEffectFailures"):
            raise ConfigApplyError(result)
        return result

    def send_bytes(self, method: str, path: str, data: bytes, content_type: str = "application/octet-stream") -> Any:
        return self._json(self._http.request(method, path, content=data, headers={"Content-Type": content_type}))

    def post_file(self, path: str, filename: str, data: bytes, extra: dict[str, str] | None = None) -> Any:
        with httpx.Client(headers={"X-API-Key": self._config.api_key}, timeout=120) as client:
            return self._json(client.post(self._config.api_url + path, files={"file": (filename, data)}, data=extra or {}))

    def events(self, path: str, *, method: str = "GET", body: Any = None, timeout: float | None = None) -> Iterator[dict]:
        with self._http.stream(method, path, content=json.dumps(body) if body is not None else None, timeout=timeout) as res:
            self._check(res)
            event, data, event_id = "message", [], None
            for line in res.iter_lines():
                if not line:
                    if data:
                        yield {"event": event, "data": "\n".join(data), "id": event_id}
                    event, data = "message", []
                    continue
                if line.startswith(":"):
                    continue
                field, _, value = line.partition(":")
                value = value[1:] if value.startswith(" ") else value
                if field == "data":
                    data.append(value)
                elif field == "event":
                    event = value
                elif field == "id" and "\0" not in value:
                    event_id = value

    def stream_sse(self, path: str) -> Iterator[str]:
        for event in self.events(path):
            yield event["data"]

    def close(self) -> None:
        self._http.close()
