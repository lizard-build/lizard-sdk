from __future__ import annotations
import time
import json
from .client import query
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
    start_command: str | None = None
    build_command: str | None = None
    container_port: int | None = None

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
            start_command=d.get("startCommand"), build_command=d.get("buildCommand"), container_port=d.get("containerPort"),
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

    def __init__(self, client: "PlatformClient", service_id: str, build_id: str | None = None) -> None:
        self._client = client
        self.service_id = service_id
        self.build_id = build_id

    def logs(self) -> Iterator[str]:
        """Stream build logs until the server closes the build stream."""
        build_id = self.build_id
        if not build_id:
            builds = self._client.get(f"/api/apps/{self.service_id}").get("builds", [])
            if not builds:
                raise LizardError("No build found for this deploy")
            build_id = builds[0]["id"]
        for event in self._client.events(f"/api/builds/{build_id}/logs"):
            if event["event"] == "error":
                raise LizardError(event["data"])
            if event["event"] == "done":
                return
            try:
                data = json.loads(event["data"])
            except ValueError:
                data = event["data"]
            yield data if isinstance(data, str) else event["data"]

    def wait(self, *, timeout_ms: int = 10 * 60_000, poll_ms: int = 3000) -> dict:
        """
        Block until the deploy reaches a terminal state.

        Returns ``{"url": str | None, "status": str}`` on success.
        Raises ``LizardError`` on failure or ``TimeoutError`` on timeout.
        """
        deadline = time.time() + timeout_ms / 1000
        while time.time() < deadline:
            build_done = True
            if self.build_id:
                build = self._client.get(f"/api/builds/{self.build_id}")
                if build["status"] in ("failed", "cancelled"):
                    raise LizardError(f"Deploy {build['status']}")
                build_done = build["status"] == "done"
            svc_dict = self._client.get(f"/api/apps/{self.service_id}")
            deploy_status = svc_dict.get("deployStatus", "")
            status = svc_dict.get("status", "")
            if deploy_status == "idle":
                if build_done and status == "running":
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
        pre_deploy_command: str | None = None,
        dockerfile_path: str | None = None,
        root_directory: str | None = None,
        wait_for_deploy: bool = False,
        env_vars: dict[str, str] | None = None,
        skip_initial_deploy: bool | None = None,
        cpu_limit: str | None = None,
        memory_limit: str | None = None,
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
            "preDeployCommand": pre_deploy_command,
            "dockerfilePath": dockerfile_path,
            "context": root_directory,
            "envVars": env_vars,
            "skipInitialDeploy": skip_initial_deploy,
            "cpuLimit": cpu_limit,
            "memoryLimit": memory_limit,
            "containerPort": port,
            "region": region,
        }
        svc = self._client.post(f"/api/projects/{project_id}/apps", {k: v for k, v in body.items() if v is not None})
        handle = DeployHandle(self._client, svc["id"], svc.get("buildId"))
        if wait_for_deploy:
            handle.wait()
        return handle

    def upload(self, *, project_id: str, source: bytes, name: str | None = None,
               service_id: str | None = None, start_command: str | None = None,
               build_command: str | None = None, pre_deploy_command: str | None = None,
               port: int | None = None, region: str | None = None) -> DeployHandle:
        if not name and not service_id:
            raise ValueError("name or service_id is required")
        path = query(f"/api/projects/{project_id}/apps/upload", name=name, appId=service_id,
                     startCommand=start_command, buildCommand=build_command,
                     preDeployCommand=pre_deploy_command, port=port, region=region)
        result = self._client.send_bytes("POST", path, source)
        return DeployHandle(self._client, result["id"], result.get("buildId"))

    def redeploy(self, id: str) -> DeployHandle:
        """Trigger a redeploy (rebuild from current source)."""
        build = self._client.post(f"/api/apps/{id}/redeploy")
        return DeployHandle(self._client, id, build["id"])

    def restart(self, id: str) -> None:
        """Restart a service without rebuilding."""
        self._client.post(f"/api/apps/{id}/restart")

    def scale(self, id: str, *, replicas: int | None = None, cpu_millis: int | None = None,
              memory_mi: int | None = None, storage_mi: int | None = None) -> None:
        if storage_mi is not None:
            raise ValueError("Storage scaling is only supported for addons")
        if replicas is not None:
            self._client.patch(f"/api/apps/{id}/scale", {"replicas": replicas})
        opts = {}
        if cpu_millis is not None:
            opts["cpuLimit"] = f"{cpu_millis}m"
        if memory_mi is not None:
            opts["memoryLimit"] = f"{memory_mi}Mi"
        if opts:
            self.update(id, opts)

    def update(self, id: str, opts: dict, *, revision: int | None = None, force: bool = False) -> dict:
        svc = self.get(id)
        if not force and revision is None:
            revision = self._client.get(f"/api/projects/{svc.project_id}")["configRevision"]
        body = {"services": [{"name": svc.name, **opts, "id": id}]}
        if not force and revision is not None:
            body["revision"] = revision
        return self._client.apply_config(svc.project_id, body)

    def logs(self, id: str, *, limit: int = 200, since: str | None = None) -> list[LogLine]:
        svc = self.get(id)
        result = self._client.get(query(f"/api/projects/{svc.project_id}/logs", service=svc.name, limit=limit, since=since))
        rows = result if isinstance(result, list) else result.get("logs", [])
        return [LogLine._from_dict(row) if isinstance(row, dict) else LogLine("info", str(row), 0) for row in rows]

    def exec_(self, id: str, cmd: str, *, timeout_ms: int = 300_000) -> dict:
        result = {"stdout": "", "stderr": "", "exitCode": None}
        for event in self._client.events(f"/api/apps/{id}/exec", method="POST", body={"cmd": cmd}, timeout=timeout_ms / 1000):
            if event["event"] == "error":
                raise LizardError(event["data"])
            data = json.loads(event["data"])
            if data.get("stream") in ("stdout", "stderr"):
                result[data["stream"]] += data.get("line", "") + "\n"
            if event["event"] == "exit":
                result["exitCode"] = data["exitCode"]
        if result["exitCode"] is None:
            raise LizardError("Exec stream ended without exit status")
        return result

    def events(self, id: str, *, build_id: str | None = None) -> list[dict]:
        return self._client.get(query(f"/api/apps/{id}/deploy-events", buildId=build_id))

    def pods(self, id: str) -> dict:
        return self._client.get(f"/api/apps/{id}/pod-status")

    def history(self, id: str, *, limit: int | None = None, before: str | None = None, level: str | None = None):
        return self._client.get(query(f"/api/apps/{id}/logs/history", limit=limit, before=before, level=level))

    def stream_logs(self, id: str):
        return self._client.events(f"/api/apps/{id}/logs")

    def build_logs(self, build_id: str):
        return self._client.events(f"/api/builds/{build_id}/logs")

    def delete(self, id: str) -> None:
        """Delete a service."""
        self._client.delete(f"/api/apps/{id}")
