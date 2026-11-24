from .client import PlatformClient, query, segment
from ..config import path_segment as _q


class StorageAPI:
    def __init__(self, client: PlatformClient):
        self._client = client

    def list(self, project_id: str, addon_id: str, *, bucket: str = "default", prefix: str | None = None):
        return self._client.get(query(f"/api/projects/{_q(project_id)}/addons/{_q(addon_id)}/s3/buckets/{segment(bucket)}/objects", prefix=prefix))

    def upload(self, project_id: str, addon_id: str, *, key: str, source: bytes, bucket: str = "default", content_type: str = "application/octet-stream"):
        key = "/".join(segment(part) for part in key.split("/"))
        return self._client.send_bytes("PUT", f"/api/projects/{_q(project_id)}/addons/{_q(addon_id)}/s3/objects/{segment(bucket)}/{key}", source, content_type)
