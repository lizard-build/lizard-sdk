import os

DEFAULT_API_URL = "https://lizard.build"
DEFAULT_SANDBOX_TIMEOUT_MS = 5 * 60 * 1000  # 5 minutes


class ConnectionConfig:
    def __init__(
        self,
        api_key: str | None = None,
        api_url: str | None = None,
        timeout_ms: int | None = None,
    ):
        self.api_key = api_key or os.environ.get("LIZARD_API_KEY", "")
        self.api_url = api_url or os.environ.get("LIZARD_API_URL", DEFAULT_API_URL)
        self.timeout_ms = timeout_ms or DEFAULT_SANDBOX_TIMEOUT_MS

        if not self.api_key:
            raise ValueError(
                "Lizard API key is required. Set LIZARD_API_KEY env var or pass api_key."
            )

    @property
    def headers(self) -> dict[str, str]:
        return {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }
