from __future__ import annotations

from .config import ConnectionConfig
from .errors import LizardError
from .platform import (
    AddonsAPI,
    DomainsAPI,
    MetricsAPI,
    PlatformClient,
    ProjectsAPI,
    SecretsAPI,
    ServicesAPI,
)
from .project import resolve_project_id
from .sandbox import Sandbox, SandboxInfo


class Lizard:
    """
    The Lizard client — entry point for the platform and sandbox APIs.

    When ``project`` is set the client is pinned to one project; every sandbox
    it creates is attributed to that project. ``project`` is optional when using
    only the platform namespace (``lizard.projects``, ``lizard.services``, …).

    Example (sandbox)::

        from lizard import Lizard

        lizard = Lizard(project="my-project")  # api_key from LIZARD_API_KEY
        sandbox = lizard.create("base")
        sandbox.process.exec_("echo hello")
        sandbox.kill()

    Example (platform API)::

        from lizard import Lizard

        lz = Lizard()
        projects = lz.projects.list()
        deploy = lz.services.upload(project_id=projects[0].id, name="api", source=data)
        result = deploy.wait()
        print("URL:", result["url"])
    """

    def __init__(
        self,
        *,
        project: str | None = None,
        api_key: str | None = None,
        api_url: str | None = None,
        timeout_ms: int | None = None,
    ):
        self._config = ConnectionConfig(api_key=api_key, api_url=api_url, timeout_ms=timeout_ms)
        self._project_ref = project

        _pc = PlatformClient(self._config)
        self.projects = ProjectsAPI(_pc)
        self.services = ServicesAPI(_pc)
        self.addons = AddonsAPI(_pc)
        self.secrets = SecretsAPI(_pc)
        self.domains = DomainsAPI(_pc)
        self.metrics = MetricsAPI(_pc)

    def project_id(self) -> str:
        """Resolve the client's project reference to a stable project ID (cached)."""
        if not self._project_ref:
            raise LizardError("No project set. Pass project= to Lizard() for sandbox operations.")
        return resolve_project_id(self._project_ref, self._config)

    def create(
        self,
        template: str | None = None,
        *,
        timeout_ms: int | None = None,
        metadata: dict[str, str] | None = None,
        envs: dict[str, str] | None = None,
        volume_id: str | None = None,
    ) -> Sandbox:
        """Create a new sandbox in this client's project."""
        return Sandbox.create(
            template,
            api_key=self._config.api_key,
            api_url=self._config.api_url,
            timeout_ms=timeout_ms if timeout_ms is not None else self._config.timeout_ms,
            metadata=metadata,
            envs=envs,
            volume_id=volume_id,
            project_id=self.project_id(),
        )

    def connect(self, sandbox_id: str) -> Sandbox:
        """Connect to an existing sandbox by ID (resumes it if paused)."""
        return Sandbox.connect(
            sandbox_id, api_key=self._config.api_key, api_url=self._config.api_url
        )

    def list(self) -> list[SandboxInfo]:
        """List running sandboxes for the authenticated account."""
        return Sandbox.list(api_key=self._config.api_key, api_url=self._config.api_url)
