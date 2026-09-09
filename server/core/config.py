"""Environment configuration shared by the API and database layer."""

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql+psycopg://kyron:kyron_dev@localhost:5432/kyron"
    )
    simulator_url: str = os.getenv("SIMULATOR_URL", "http://localhost:8090")


settings = Settings()
