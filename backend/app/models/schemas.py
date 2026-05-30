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


class HostFirmware(BaseModel):
    """The host firmware (Klipper / Kalico) version + Klippy state."""

    version: str | None = None
    state: str | None = None


class McuFirmware(BaseModel):
    """A single MCU's reported firmware version and whether it matches the host."""

    name: str
    version: str | None = None
    in_sync: bool | None = None


class FirmwareTools(BaseModel):
    """Availability of the local firmware toolchain."""

    klipper: bool
    katapult: bool
    flashtool: bool
    dfu_util: bool
    avrdude: bool
    can_utils: bool


class FirmwareStatus(BaseModel):
    """Read-only firmware status for the Firmware Upgrade widget."""

    reachable: bool
    host: HostFirmware
    mcus: list[McuFirmware]
    tools: FirmwareTools
