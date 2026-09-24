from __future__ import annotations
from dataclasses import dataclass

from .config import ConnectionConfig, HTTP_TIMEOUT_S


@dataclass
class VolumeInfo:
    """Metadata for a persistent volume."""

    id: str
    project_id: str
    name: str
    size_gb: int
    status: str
    created_at: int
    attached_to: str | None = None
    #: Region the volume's node lives in. A sandbox mounting it runs here too.
    region: str | None = None


class Volume:
    """
    A persistent volume that outlives sandboxes.

    A volume's **name** is its key inside a project: names are unique per project,
    and every method here accepts either a name or the generated id wherever a
    volume is addressed. Prefer the name -- it is the thing you chose and can
    reconstruct, while the id only exists after the first create.

    Names are slugs: lowercase letters, digits and dashes, starting and ending with
    a letter or digit, up to 64 characters.

    Mount it to a sandbox with ``Sandbox.create(volume_name="my-data")``; inside the
    microVM it appears at ``/workspace``.

    Example::

        from lizard import Sandbox, Volume

        volume = Volume.get_or_create("proj_abc123", "my-data", size_gb=5)
        sandbox = Sandbox.create("base", project_id="proj_abc123", volume_name="my-data")
        sandbox.process.exec_("echo hello > /workspace/file.txt")
        sandbox.kill()  # volume persists
    """

    def __init__(
        self,
        volume_id: str,
        *,
        name: str | None = None,
        api_key: str | None = None,
        api_url: str | None = None,
    ):
        self.volume_id = volume_id
        #: The volume's name: unique within its project, usable anywhere the id is.
        self.name = name
        self._config = ConnectionConfig(api_key=api_key, api_url=api_url)

    @classmethod
    def create(
        cls,
        project_id: str,
        name: str,
        *,
        size_gb: int = 5,
        region: str | None = None,
        api_key: str | None = None,
        api_url: str | None = None,
    ) -> "Volume":
        """Create a volume in a project.

        ``size_gb`` is a whole number of GB, default 5. New volumes allow 1–50 GB
        unless the server config sets another maximum.

        Raises :class:`~lizard.ConflictError` if the project already has a volume
        with this name -- use :meth:`get_or_create` when you want "make sure this
        exists" instead.

        ``region`` places the volume, e.g. ``"us-east-1"``. A volume is node-local,
        so this also fixes where any sandbox mounting it must run --
        :meth:`Sandbox.create` takes the volume's region automatically when you do
        not name one, so you normally set the region here or nowhere. Defaults to
        the platform's default region.
        """
        import httpx

        config = ConnectionConfig(api_key=api_key, api_url=api_url)
        res = httpx.post(
            f"{config.api_url}/api/projects/{project_id}/volumes",
            headers=config.headers,
            json=_body(name, size_gb, region),
            timeout=HTTP_TIMEOUT_S,
        )
        if not res.is_success:
            from .errors import handle_api_error
            handle_api_error(res.status_code, res.text)

        body = res.json()
        return cls(body["id"], name=body.get("name", name), api_key=api_key, api_url=api_url)

    @classmethod
    def get_or_create(
        cls,
        project_id: str,
        name: str,
        *,
        size_gb: int = 5,
        region: str | None = None,
        api_key: str | None = None,
        api_url: str | None = None,
    ) -> "Volume":
        """Return the project's volume with this name, creating it if absent.

        This is the reason a volume's name is its key: an agent that wants "the
        scratch disk for this task" no longer has to store an id between runs.

        New volumes allow 1–50 GB (default 5), subject to server config.
        An existing volume is returned as-is -- ``size_gb`` applies only to a fresh
        create and never resizes one that is already there.
        """
        import httpx

        config = ConnectionConfig(api_key=api_key, api_url=api_url)
        res = httpx.post(
            f"{config.api_url}/api/projects/{project_id}/volumes",
            headers=config.headers,
            json={**_body(name, size_gb, region), "getOrCreate": True},
            timeout=HTTP_TIMEOUT_S,
        )
        if not res.is_success:
            from .errors import handle_api_error
            handle_api_error(res.status_code, res.text)

        body = res.json()
        return cls(body["id"], name=body.get("name", name), api_key=api_key, api_url=api_url)

    @classmethod
    def get(
        cls,
        project_id: str,
        name_or_id: str,
        *,
        api_key: str | None = None,
        api_url: str | None = None,
    ) -> "Volume":
        """Look up an existing volume by name or by id."""
        import httpx
        from urllib.parse import quote

        config = ConnectionConfig(api_key=api_key, api_url=api_url)
        res = httpx.get(
            f"{config.api_url}/api/projects/{project_id}/volumes/{quote(name_or_id, safe='')}",
            headers=config.headers,
            timeout=HTTP_TIMEOUT_S,
        )
        if not res.is_success:
            from .errors import handle_api_error
            handle_api_error(res.status_code, res.text)

        body = res.json()
        return cls(body["id"], name=body.get("name"), api_key=api_key, api_url=api_url)

    @classmethod
    def remove(
        cls,
        project_id: str,
        name_or_id: str,
        *,
        api_key: str | None = None,
        api_url: str | None = None,
    ) -> None:
        """Delete a volume by name or by id, without constructing one first."""
        import httpx
        from urllib.parse import quote

        config = ConnectionConfig(api_key=api_key, api_url=api_url)
        res = httpx.delete(
            f"{config.api_url}/api/projects/{project_id}/volumes/{quote(name_or_id, safe='')}",
            headers=config.headers,
            timeout=HTTP_TIMEOUT_S,
        )
        if not res.is_success:
            from .errors import handle_api_error
            handle_api_error(res.status_code, res.text)

    @classmethod
    def list(
        cls,
        project_id: str,
        *,
        api_key: str | None = None,
        api_url: str | None = None,
    ) -> list[VolumeInfo]:
        """List all volumes in a project."""
        import httpx

        config = ConnectionConfig(api_key=api_key, api_url=api_url)
        res = httpx.get(
            f"{config.api_url}/api/projects/{project_id}/volumes",
            headers=config.headers,
            timeout=HTTP_TIMEOUT_S,
        )
        if not res.is_success:
            from .errors import handle_api_error
            handle_api_error(res.status_code, res.text)

        return [_to_info(v) for v in res.json()]

    def get_info(self, project_id: str) -> VolumeInfo:
        """Get metadata about this volume."""
        import httpx

        res = httpx.get(
            f"{self._config.api_url}/api/projects/{project_id}/volumes/{self.volume_id}",
            headers=self._config.headers,
            timeout=HTTP_TIMEOUT_S,
        )
        if not res.is_success:
            from .errors import handle_api_error
            handle_api_error(res.status_code, res.text)

        return _to_info(res.json())

    def delete(self, project_id: str) -> None:
        """Delete this volume and the data on it."""
        import httpx

        res = httpx.delete(
            f"{self._config.api_url}/api/projects/{project_id}/volumes/{self.volume_id}",
            headers=self._config.headers,
            timeout=HTTP_TIMEOUT_S,
        )
        if not res.is_success:
            from .errors import handle_api_error
            handle_api_error(res.status_code, res.text)


def _body(name: str, size_gb: int, region: str | None) -> dict:
    """The create body, with ``region`` omitted rather than null when unset.

    ``json.dumps`` renders ``None`` as a JSON ``null``, where JavaScript's
    ``JSON.stringify`` drops an ``undefined`` key entirely. The server's schema has
    ``region`` as optional, not nullable, so sending an explicit null was a 400 on
    every create that did not name a region -- which is the common case, since the
    region normally comes from the volume.
    """
    body: dict = {"name": name, "sizeGb": size_gb}
    if region is not None:
        body["region"] = region
    return body


def _to_info(v: dict) -> VolumeInfo:
    return VolumeInfo(
        id=v["id"],
        project_id=v["projectId"],
        name=v["name"],
        size_gb=v["sizeGb"],
        status=v["status"],
        created_at=v["createdAt"],
        attached_to=v.get("attachedTo"),
        region=v.get("region"),
    )
