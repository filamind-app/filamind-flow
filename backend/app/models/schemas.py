from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Liveness payload for the backend service itself."""

    status: str
    service: str
    version: str


class MoonrakerStatus(BaseModel):
    """Result of a backend-side reachability probe against Moonraker."""

    reachable: bool
    moonraker_url: str
    klippy_state: str | None = None
    detail: str | None = None
