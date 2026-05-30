from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, overridable via FILAMIND_* env vars or a .env file."""

    model_config = SettingsConfigDict(env_prefix="FILAMIND_", env_file=".env", extra="ignore")

    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"

    # Base URL of the Moonraker instance this panel sits in front of.
    moonraker_url: str = "http://localhost:7125"

    # Browser origins allowed to call this API (i.e. where the frontend is served).
    cors_origins: list[str] = ["http://localhost:5173"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Accepts a comma-separated string in addition to a JSON/list value."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    """Returns a cached Settings instance."""
    return Settings()
