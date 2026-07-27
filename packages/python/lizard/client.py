from __future__ import annotations

from .config import ConnectionConfig
from .errors import LizardError
from .project import resolve_project_id
from .sandbox import Sandbox, SandboxInfo


class Lizard:
    """
    The Lizard client — the entry point for creating sandboxes.

    A client is pinned to one project (billing is metered per project), so every
    sandbox it creates is attributed correctly. The project reference — ID, slug,
    or name — is resolved to a project ID on first use and cached.

    Example::

        from lizard import Lizard

        lizard = Lizard(project="my-project")  # api_key from LIZARD_API_KEY

        sandbox = lizard.create("base")
        sandbox.process.exec_("echo hello")
        sandbox.kill()
    """

    def __init__(
        self,
        *,
        project: str,
        api_key: str | None = None,
        api_url: str | None = None,
        timeout_ms: int | None = None,
    ):
        if not project:
            raise LizardError(
                'A project is required. Pass project (its ID, slug, or name): '
                'Lizard(project="my-project").'
            )
        self._config = ConnectionConfig(api_key=api_key, api_url=api_url, timeout_ms=timeout_ms)
        self._project_ref = project

    def project_id(self) -> str:
        """Resolve the client's project reference to a stable project ID (cached)."""
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
