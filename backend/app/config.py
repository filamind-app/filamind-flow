from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, overridable via FILAMIND_* env vars or a .env file."""

    model_config = SettingsConfigDict(env_prefix="FILAMIND_", env_file=".env", extra="ignore")

    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"

    # Base URL of the Moonraker instance this panel sits in front of.
    moonraker_url: str = "http://localhost:7125"

    # Firmware toolchain locations (Firmware Upgrade widget).
    klipper_dir: str = "~/klipper"
    katapult_dir: str = "~/katapult"

    # Comma-separated browser origins allowed to call this API.
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        """The configured CORS origins as a list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Returns a cached Settings instance."""
    return Settings()
