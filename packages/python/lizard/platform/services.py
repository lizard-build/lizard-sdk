from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Iterator

if TYPE_CHECKING:
    from .client import PlatformClient

from ..errors import LizardError, TimeoutError as LizardTimeoutError


@dataclass
class Service:
    id: str
    name: str
    project_id: str
    status: str
    deploy_status: str
    domain: str | None = None
    region: str | None = None
    source_type: str | None = None
    repo_url: str | None = None
    branch: str | None = None

    @classmethod
    def _from_dict(cls, d: dict) -> "Service":
        return cls(
            id=d["id"],
            name=d["name"],
            project_id=d.get("projectId", ""),
            status=d.get("status", "none"),
            deploy_status=d.get("deployStatus", "idle"),
            domain=d.get("domain"),
            region=d.get("region"),
            source_type=d.get("sourceType"),
            repo_url=d.get("repoUrl"),
            branch=d.get("branch"),
        )


@dataclass
class LogLine:
    level: str
    message: str
    ts: int
    service: str | None = None
    replica: str | None = None

    @classmethod
    def _from_dict(cls, d: dict) -> "LogLine":
        return cls(
            level=d.get("level", "info"),
            message=d.get("message", ""),
            ts=int(d.get("ts", 0)),
            service=d.get("service"),
            replica=d.get("replica"),
        )


class DeployHandle:
    """
    Handle for a running deploy. Poll for completion or stream logs.

    Example::

        deploy = lizard.services.upload(project_id=pid, name="api", source=data)
        for line in deploy.logs():
            print(line)
        result = deploy.wait()
        print("Deployed to", result["url"])
    """

    def __init__(self, client: "PlatformClient", service_id: str) -> None:
        self._client = client
        self.service_id = service_id

    def logs(self, limit: int = 200) -> list[str]:
        """Return recent log lines."""
        try:
            result = self._client.get(f"/api/apps/{self.service_id}/logs?limit={limit}")
            if isinstance(result, list):
                return [l if isinstance(l, str) else str(l) for l in result]
            return [l if isinstance(l, str) else str(l) for l in result.get("logs", [])]
        except Exception:
            return []

    def wait(self, *, timeout_ms: int = 10 * 60_000, poll_ms: int = 3000) -> dict:
        """
        Block until the deploy reaches a terminal state.

        Returns ``{"url": str | None, "status": str}`` on success.
        Raises ``LizardError`` on failure or ``TimeoutError`` on timeout.
        """
        deadline = time.time() + timeout_ms / 1000
        while time.time() < deadline:
            svc_dict = self._client.get(f"/api/apps/{self.service_id}")
            deploy_status = svc_dict.get("deployStatus", "")
            status = svc_dict.get("status", "")
            if deploy_status == "idle":
                if status == "running":
                    domain = svc_dict.get("domain")
                    return {"url": f"https://{domain}" if domain else None, "status": "running"}
                if status == "crashed":
                    raise LizardError("Service crashed after deploy")
            if deploy_status == "failed":
                raise LizardError("Deploy failed")
            time.sleep(poll_ms / 1000)
        raise LizardTimeoutError(f"Deploy did not complete within {timeout_ms}ms")


class ServicesAPI:
    def __init__(self, client: "PlatformClient") -> None:
        self._client = client

    def list(self, *, project_id: str) -> list[Service]:
        """List all services in a project."""
        return [Service._from_dict(s) for s in self._client.get(f"/api/projects/{project_id}/apps")]

    def get(self, id: str) -> Service:
        """Get a service by ID."""
        return Service._from_dict(self._client.get(f"/api/apps/{id}"))

    def deploy(
        self,
        *,
        project_id: str,
        name: str,
        repo_url: str | None = None,
        branch: str = "main",
        source_type: str = "github",
        start_command: str | None = None,
        build_command: str | None = None,
        port: int | None = None,
        region: str | None = None,
    ) -> DeployHandle:
        """Create a service and kick off a git-source deploy."""
        body = {
            "name": name,
            "sourceType": source_type,
            "repoUrl": repo_url,
            "branch": branch,
            "startCommand": start_command,
            "buildCommand": build_command,
            "containerPort": port,
            "region": region,
        }
        svc = self._client.post(f"/api/projects/{project_id}/apps", {k: v for k, v in body.items() if v is not None})
        return DeployHandle(self._client, svc["id"])

    def upload(
        self,
        *,
        project_id: str,
        name: str,
        source: bytes,
        start_command: str | None = None,
        build_command: str | None = None,
        port: int | None = None,
        region: str | None = None,
    ) -> DeployHandle:
        """Upload a `.tar.gz` tarball and deploy it."""
        extra: dict[str, str] = {"name": name}
        if start_command:
            extra["startCommand"] = start_command
        if build_command:
            extra["buildCommand"] = build_command
        if port is not None:
            extra["containerPort"] = str(port)
        if region:
            extra["region"] = region
        result = self._client.post_file(
            f"/api/projects/{project_id}/apps/upload",
            "source.tar.gz",
            source,
            extra,
        )
        return DeployHandle(self._client, result["id"])

    def redeploy(self, id: str) -> DeployHandle:
        """Trigger a redeploy (rebuild from current source)."""
        self._client.post(f"/api/apps/{id}/redeploy")
        return DeployHandle(self._client, id)

    def restart(self, id: str) -> None:
        """Restart a service without rebuilding."""
        self._client.post(f"/api/apps/{id}/restart")

    def scale(
        self,
        id: str,
        *,
        replicas: int | None = None,
        cpu_millis: int | None = None,
        memory_mi: int | None = None,
        storage_mi: int | None = None,
    ) -> None:
        """Scale a service."""
        body = {k: v for k, v in {
            "replicas": replicas,
            "cpuMillis": cpu_millis,
            "memoryMi": memory_mi,
            "storageMi": storage_mi,
        }.items() if v is not None}
        self._client.post(f"/api/apps/{id}/scale", body)

    def logs(self, id: str, *, limit: int = 200) -> list[LogLine]:
        """Get recent log lines."""
        result = self._client.get(f"/api/apps/{id}/logs?limit={limit}")
        rows = result if isinstance(result, list) else result.get("logs", [])
        return [LogLine._from_dict(l) if isinstance(l, dict) else LogLine(level="info", message=str(l), ts=0)
                for l in rows]

    def exec_(self, id: str, cmd: str, *, timeout_ms: int | None = None) -> dict:
        """Execute a command inside the running service container."""
        body = {"cmd": cmd}
        if timeout_ms is not None:
            body["timeoutMs"] = str(timeout_ms)
        return self._client.post(f"/api/apps/{id}/exec", body)

    def delete(self, id: str) -> None:
        """Delete a service."""
        self._client.delete(f"/api/apps/{id}")
