from .client import PlatformClient
from .services import ServicesAPI


class GitHubAPI:
    def __init__(self, client: PlatformClient):
        self._client = client

    def status(self):
        return self._client.get("/api/github/status")

    def install_url(self) -> str:
        """Complete the GitHub App installation in a browser using the caller's account."""
        return self._client._config.api_url + "/api/auth/github/install"

    def checkout(self, service_id: str, branch: str):
        services = ServicesAPI(self._client)
        services.update(service_id, {"branch": branch})
        return services.redeploy(service_id)
