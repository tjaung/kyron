"""Environment configuration shared by the API and database layer."""

from dataclasses import dataclass
import os
import secrets


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql+psycopg://kyron:kyron_dev@localhost:5432/kyron"
    )
    simulator_url: str = os.getenv("SIMULATOR_URL", "http://localhost:8090")
    jwt_secret: str = os.getenv("JWT_SECRET") or secrets.token_urlsafe(48)
    simulator_token: str = os.getenv("SIMULATOR_TOKEN", "")
    client_url: str = os.getenv("CLIENT_URL", "http://localhost:5173")
    cookie_secure: bool = os.getenv("COOKIE_SECURE", "false").lower() == "true"
    session_seconds: int = 8 * 60 * 60


settings = Settings()
