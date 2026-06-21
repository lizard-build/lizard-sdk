from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import ConnectionConfig


@dataclass
class FileInfo:
    """Metadata for a file or directory inside a Lizard sandbox microVM."""

    name: str
    path: str
    type: str  # 'file' | 'dir'
    size: int


class Fs:
    """
    Read and write files inside a Lizard sandbox microVM.

    Access via ``sandbox.fs``.
    """

    def __init__(self, sandbox_id: str, config: "ConnectionConfig"):
        self._sandbox_id = sandbox_id
        self._config = config

    def write(self, path: str, data: str | bytes, *, user: str | None = None) -> None:
        """
        Write a file into the microVM filesystem.

        Parent directories are created automatically if they don't exist.

        :param path: Absolute path inside the microVM.
        :param data: File contents — string or bytes.
        :param user: Write as this Linux user (default: ``root``).

        Example::

            sandbox.fs.write("/app/index.js", 'console.log("hello")')
        """
        import httpx

        content = data if isinstance(data, str) else data.decode()
        body: dict = {"path": path, "content": content}
        if user:
            body["user"] = user

        res = httpx.post(
            f"{self._config.api_url}/api/sandboxes/{self._sandbox_id}/files",
            headers=self._config.headers,
            json=body,
        )
        if not res.is_success:
            from ..errors import handle_api_error
            handle_api_error(res.status_code, res.text)

    def read(self, path: str, *, user: str | None = None) -> str:
        """
        Read a file from the microVM filesystem.

        :param path: Absolute path inside the microVM.
        :returns: File contents as a UTF-8 string.

        Example::

            content = sandbox.fs.read("/app/index.js")
        """
        import httpx

        params: dict = {"path": path}
        if user:
            params["user"] = user

        res = httpx.get(
            f"{self._config.api_url}/api/sandboxes/{self._sandbox_id}/files",
            headers=self._config.headers,
            params=params,
        )
        if not res.is_success:
            from ..errors import handle_api_error
            handle_api_error(res.status_code, res.text)
        return res.text

    def list(self, path: str, *, user: str | None = None) -> list[FileInfo]:
        """
        List files and directories at a path inside the microVM.

        :param path: Directory path to list.

        Example::

            entries = sandbox.fs.list("/app")
        """
        import httpx

        params: dict = {"path": path}
        if user:
            params["user"] = user

        res = httpx.get(
            f"{self._config.api_url}/api/sandboxes/{self._sandbox_id}/files/list",
            headers=self._config.headers,
            params=params,
        )
        if not res.is_success:
            from ..errors import handle_api_error
            handle_api_error(res.status_code, res.text)

        return [FileInfo(**f) for f in res.json()]

    def remove(self, path: str, *, user: str | None = None) -> None:
        """Remove a file or directory from the microVM filesystem."""
        import httpx

        body: dict = {"path": path}
        if user:
            body["user"] = user

        res = httpx.request(
            "DELETE",
            f"{self._config.api_url}/api/sandboxes/{self._sandbox_id}/files",
            headers=self._config.headers,
            json=body,
        )
        if not res.is_success:
            from ..errors import handle_api_error
            handle_api_error(res.status_code, res.text)

    def make_dir(self, path: str, *, user: str | None = None) -> None:
        """Create a directory (and any missing parents) inside the microVM."""
        import httpx
        import json

        body: dict = {"cmd": f"mkdir -p {json.dumps(path)}"}
        if user:
            body["user"] = user

        res = httpx.post(
            f"{self._config.api_url}/api/sandboxes/{self._sandbox_id}/exec",
            headers=self._config.headers,
            json=body,
        )
        if not res.is_success:
            from ..errors import handle_api_error
            handle_api_error(res.status_code, res.text)
