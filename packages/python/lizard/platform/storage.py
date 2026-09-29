from .client import PlatformClient, query, segment


class StorageAPI:
    def __init__(self, client: PlatformClient):
        self._client = client

    def list(self, project_id: str, addon_id: str, *, bucket: str = "default", prefix: str | None = None):
        return self._client.get(query(f"/api/projects/{project_id}/addons/{addon_id}/s3/buckets/{segment(bucket)}/objects", prefix=prefix))

    def upload(self, project_id: str, addon_id: str, *, key: str, source: bytes, bucket: str = "default", content_type: str = "application/octet-stream"):
        key = "/".join(segment(part) for part in key.split("/"))
        return self._client.send_bytes("PUT", f"/api/projects/{project_id}/addons/{addon_id}/s3/objects/{segment(bucket)}/{key}", source, content_type)
