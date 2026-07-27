from __future__ import annotations
from dataclasses import dataclass

from .config import ConnectionConfig


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


class Volume:
    """
    A persistent volume that outlives sandboxes.

    Mount it to a sandbox with ``Sandbox.create(volume_id=volume.volume_id)``;
    inside the microVM it appears at ``/data``.

    Example::

        from lizard import Sandbox, Volume

        volume = Volume.create("proj_abc123", "my-data", size_gb=5)
        sandbox = Sandbox.create("base", project_id="proj_abc123", volume_id=volume.volume_id)
        sandbox.process.exec_("echo hello > /data/file.txt")
        sandbox.kill()  # volume persists
    """

    def __init__(
        self,
        volume_id: str,
        *,
        api_key: str | None = None,
        api_url: str | None = None,
    ):
        self.volume_id = volume_id
        self._config = ConnectionConfig(api_key=api_key, api_url=api_url)

    @classmethod
    def create(
        cls,
        project_id: str,
        name: str,
        *,
        size_gb: int = 5,
        api_key: str | None = None,
        api_url: str | None = None,
    ) -> "Volume":
        """Create a volume in a project."""
        import httpx

        config = ConnectionConfig(api_key=api_key, api_url=api_url)
        res = httpx.post(
            f"{config.api_url}/api/projects/{project_id}/volumes",
            headers=config.headers,
            json={"name": name, "sizeGb": size_gb},
        )
        if not res.is_success:
            from .errors import handle_api_error
            handle_api_error(res.status_code, res.text)

        return cls(res.json()["id"], api_key=api_key, api_url=api_url)

    @classmethod
    def get(
        cls,
        project_id: str,
        volume_id: str,
        *,
        api_key: str | None = None,
        api_url: str | None = None,
    ) -> "Volume":
        """Look up an existing volume by ID."""
        import httpx

        config = ConnectionConfig(api_key=api_key, api_url=api_url)
        res = httpx.get(
            f"{config.api_url}/api/projects/{project_id}/volumes/{volume_id}",
            headers=config.headers,
        )
        if not res.is_success:
            from .errors import handle_api_error
            handle_api_error(res.status_code, res.text)

        return cls(volume_id, api_key=api_key, api_url=api_url)

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
        )
        if not res.is_success:
            from .errors import handle_api_error
            handle_api_error(res.status_code, res.text)


def _to_info(v: dict) -> VolumeInfo:
    return VolumeInfo(
        id=v["id"],
        project_id=v["projectId"],
        name=v["name"],
        size_gb=v["sizeGb"],
        status=v["status"],
        created_at=v["createdAt"],
        attached_to=v.get("attachedTo"),
    )
