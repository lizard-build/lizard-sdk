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
    type: str  # 'file' | 'dir' | 'symlink'
    size: int
    #: Permission bits as a string, e.g. ``-rw-r--r--``. None on older sandboxes.
    mode: str | None = None
    #: Last modification time, unix milliseconds. None on older sandboxes.
    mod_time: int | None = None


@dataclass
class FsEvent:
    """A filesystem change reported by a :class:`Watcher`."""

    type: str  # create | write | remove | rename | chmod
    #: The entry's name within its directory.
    name: str
    #: Full path inside the sandbox.
    path: str


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

    def stat(self, path: str, *, user: str | None = None) -> FileInfo:
        """Metadata for a single path -- size, type, permissions, modification time.

        Saves listing a parent directory and filtering it just to answer "does
        this exist, and how big is it".

        Raises :class:`~lizard.NotFoundError` if the path does not exist.
        Sandboxes created before this shipped run a guest agent without it and
        raise :class:`~lizard.LizardError` (501) -- recreate the sandbox to use it.
        """
        import httpx

        params: dict = {"path": path}
        if user:
            params["user"] = user
        res = httpx.get(
            f"{self._config.api_url}/api/sandboxes/{self._sandbox_id}/files/stat",
            headers=self._config.headers,
            params=params,
        )
        if not res.is_success:
            from ..errors import handle_api_error
            handle_api_error(res.status_code, res.text)
        b = res.json()
        return FileInfo(
            name=b["name"],
            path=b["path"],
            type=b["type"],
            size=b["size"],
            mode=b.get("mode"),
            mod_time=b.get("modTime"),
        )

    def move(self, from_path: str, to_path: str) -> None:
        """Move or rename a path, creating the destination's parent directories.

        Sandboxes created before this shipped run a guest agent without it and
        raise :class:`~lizard.LizardError` (501) -- recreate the sandbox to use it.
        """
        import httpx

        res = httpx.post(
            f"{self._config.api_url}/api/sandboxes/{self._sandbox_id}/files/move",
            headers=self._config.headers,
            json={"from": from_path, "to": to_path},
        )
        if not res.is_success:
            from ..errors import handle_api_error
            handle_api_error(res.status_code, res.text)

    def watch(self, path: str, *, recursive: bool = False) -> "Watcher":
        """Watch a directory for changes.

        Polling rather than a push stream: the events cross two proxy hops, and a
        long-lived stream through both is exactly what breaks first. Call
        :meth:`Watcher.get_events` on whatever interval suits you -- each call
        drains everything queued since the last one, so nothing is missed between
        polls.

        Remember to :meth:`Watcher.close` it; an abandoned watcher keeps queueing
        events in the guest until the sandbox ends (bounded, but wasted).

        Sandboxes created before this shipped run a guest agent without it and
        raise :class:`~lizard.LizardError` (501) -- recreate the sandbox to use it.
        """
        import httpx

        res = httpx.post(
            f"{self._config.api_url}/api/sandboxes/{self._sandbox_id}/files/watch",
            headers=self._config.headers,
            json={"path": path, "recursive": recursive},
        )
        if not res.is_success:
            from ..errors import handle_api_error
            handle_api_error(res.status_code, res.text)
        return Watcher(self._sandbox_id, self._config, res.json()["watcherId"])


class Watcher:
    """A handle to a directory watch inside a sandbox. Created by :meth:`Fs.watch`."""

    def __init__(self, sandbox_id: str, config: "ConnectionConfig", watcher_id: str):
        self._sandbox_id = sandbox_id
        self._config = config
        #: Server-side id for this watch.
        self.watcher_id = watcher_id

    def get_events(self) -> list[FsEvent]:
        """Drain every change since the last call.

        Returns an empty list when nothing has happened -- that is not an error,
        just a quiet interval.
        """
        import httpx

        res = httpx.get(
            f"{self._config.api_url}/api/sandboxes/{self._sandbox_id}/files/watch/events",
            headers=self._config.headers,
            params={"watcherId": self.watcher_id},
        )
        if not res.is_success:
            from ..errors import handle_api_error
            handle_api_error(res.status_code, res.text)
        return [FsEvent(type=e["type"], name=e["name"], path=e["path"]) for e in res.json()]

    def close(self) -> None:
        """Stop watching and release the guest-side queue."""
        import httpx

        res = httpx.request(
            "DELETE",
            f"{self._config.api_url}/api/sandboxes/{self._sandbox_id}/files/watch",
            headers=self._config.headers,
            params={"watcherId": self.watcher_id},
        )
        if not res.is_success:
            from ..errors import handle_api_error
            handle_api_error(res.status_code, res.text)
