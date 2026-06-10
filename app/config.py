import os


class Settings:
    """Environment-driven configuration for the proxy."""

    def __init__(self) -> None:
        self.upstream_base_url: str = os.environ.get(
            "UPSTREAM_BASE_URL", "http://localhost:4000"
        ).rstrip("/")
        self.listen_host: str = os.environ.get("LISTEN_HOST", "127.0.0.1")
        self.listen_port: int = int(os.environ.get("LISTEN_PORT", "8787"))
        self.continue_text: str = os.environ.get("CONTINUE_TEXT", "Continue.")
        self.debug: bool = os.environ.get("DEBUG", "").lower() in {"1", "true", "yes", "on"}


settings = Settings()
