from __future__ import annotations

from .config import ConnectionConfig
from .errors import LizardError
from .platform import (
    AddonsAPI,
    ApiKeysAPI,
    BillingAPI,
    DomainsAPI,
    MetricsAPI,
    PlatformClient,
    ProjectsAPI,
    RegionsAPI,
    SecretsAPI,
    ServicesAPI,
    WorkspacesAPI,
)
from .project import resolve_project_id
from .sandbox import Sandbox, SandboxInfo
from .volume import Volume, VolumeInfo


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
        self._pc = _pc
        #: Create, list and delete workspaces -- the top of the ownership tree.
        self.workspaces = WorkspacesAPI(_pc)
        #: Mint and revoke API keys, including keys scoped to one workspace/project.
        self.api_keys = ApiKeysAPI(_pc)
        #: List the regions workloads can be placed in.
        self.regions = RegionsAPI(_pc)
        #: Account balance, burn rate and transactions.
        self.billing = BillingAPI(_pc)
        #: Persistent volumes in this client's project.
        self.volumes = _ProjectVolumes(self)
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
        region: str | None = None,
        volume_id: str | None = None,
        volume_name: str | None = None,
        lizard_token: str | None = None,
    ) -> Sandbox:
        """Create a new sandbox in this client's project."""
        return Sandbox.create(
            template,
            api_key=self._config.api_key,
            api_url=self._config.api_url,
            timeout_ms=timeout_ms if timeout_ms is not None else self._config.timeout_ms,
            metadata=metadata,
            envs=envs,
            region=region,
            volume_id=volume_id,
            volume_name=volume_name,
            lizard_token=lizard_token,
            project_id=self.project_id(),
        )

    def connect(self, sandbox_id: str) -> Sandbox:
        """Connect to an existing sandbox by ID. Raises NotFoundError if gone."""
        return Sandbox.connect(
            sandbox_id, api_key=self._config.api_key, api_url=self._config.api_url
        )

    def list(self) -> list[SandboxInfo]:
        """List running sandboxes for the authenticated account."""
        return Sandbox.list(api_key=self._config.api_key, api_url=self._config.api_url)

    def whoami(self) -> dict:
        """The account this credential belongs to -- the SDK's ``lizard whoami``.

        Works for a scoped key as well as a full one: the identity is the account
        that created the key, which is what the key's usage bills to.
        """
        return self._pc.get("/api/auth/me")

    @property
    def platform(self) -> PlatformClient:
        """The underlying HTTP client, for endpoints this SDK does not wrap yet."""
        return self._pc


class _ProjectVolumes:
    """Volume calls bound to a client's project -- the same as the :class:`Volume`
    classmethods, minus the ``project_id`` argument. Reached as ``lizard.volumes``.

    Example::

        lizard = Lizard(project="my-project")
        vol = lizard.volumes.get_or_create("scratch", size_gb=10)
        sb = lizard.create("codex", volume_name="scratch")
    """

    def __init__(self, parent: "Lizard") -> None:
        self._parent = parent

    def _kw(self) -> dict:
        return {
            "api_key": self._parent._config.api_key,
            "api_url": self._parent._config.api_url,
        }

    def create(self, name: str, *, size_gb: int = 5, region: str | None = None) -> Volume:
        return Volume.create(
            self._parent.project_id(), name, size_gb=size_gb, region=region, **self._kw()
        )

    def get_or_create(self, name: str, *, size_gb: int = 5, region: str | None = None) -> Volume:
        return Volume.get_or_create(
            self._parent.project_id(), name, size_gb=size_gb, region=region, **self._kw()
        )

    def get(self, name_or_id: str) -> Volume:
        return Volume.get(self._parent.project_id(), name_or_id, **self._kw())

    def list(self) -> list[VolumeInfo]:
        return Volume.list(self._parent.project_id(), **self._kw())

    def delete(self, name_or_id: str) -> None:
        Volume.delete(self._parent.project_id(), name_or_id, **self._kw())
