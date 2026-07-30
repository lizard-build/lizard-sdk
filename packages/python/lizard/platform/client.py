from __future__ import annotations
import json
from typing import Any, AsyncGenerator, Generator

import httpx

from ..config import ConnectionConfig
from ..errors import handle_api_error


class PlatformClient:
    """Shared HTTP helper for platform (non-sandbox) API calls."""

    def __init__(self, config: ConnectionConfig) -> None:
        self._config = config
        self._http = httpx.Client(
            base_url=config.api_url,
            headers={"X-API-Key": config.api_key, "Content-Type": "application/json"},
            timeout=30,
        )

    def _check(self, res: httpx.Response) -> None:
        if not res.is_success:
            try:
                msg = res.json().get("error", res.text)
            except Exception:
                msg = res.text
            handle_api_error(res.status_code, msg)

    def get(self, path: str) -> Any:
        res = self._http.get(path)
        self._check(res)
        return res.json()

    def post(self, path: str, body: Any = None) -> Any:
        res = self._http.post(path, content=json.dumps(body) if body is not None else None)
        self._check(res)
        if res.status_code == 204 or not res.content:
            return None
        return res.json()

    def patch(self, path: str, body: Any) -> Any:
        res = self._http.patch(path, content=json.dumps(body))
        self._check(res)
        return res.json()

    def delete(self, path: str, body: Any = None) -> Any:
        kwargs: dict[str, Any] = {}
        if body is not None:
            kwargs["content"] = json.dumps(body)
        res = self._http.delete(path, **kwargs)
        self._check(res)
        if res.status_code == 204 or not res.content:
            return None
        return res.json()

    def post_file(self, path: str, filename: str, data: bytes, extra: dict[str, str] | None = None) -> Any:
        files = {"file": (filename, data, "application/gzip")}
        fields = extra or {}
        res = httpx.post(
            f"{self._config.api_url}{path}",
            headers={"X-API-Key": self._config.api_key},
            files=files,
            data=fields,
            timeout=120,
        )
        self._check(res)
        return res.json()
