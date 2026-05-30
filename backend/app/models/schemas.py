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
    #: Connection type derived from the Klipper config: host / canbus / usb / serial.
    kind: str = "serial"


class HostMcu(BaseModel):
    """The optional Klipper 'Linux process' MCU running on the host (host GPIO/I2C/SPI).

    ``configured`` means an ``[mcu host]``-style section is wired into the running
    config (so it shows up as an active MCU); ``service_active`` means the host's
    ``klipper-mcu`` service is running, which can be true even when nothing uses it.
    """

    configured: bool = False
    service_active: bool = False


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
    host_mcu: HostMcu
    tools: FirmwareTools


class Board(BaseModel):
    """A discovered MCU board, merged across Moonraker + USB/CAN/DFU scans."""

    id: str
    name: str
    #: The Klipper ``[mcu]`` section name, when this board is configured.
    mcu_name: str | None = None
    #: How the board is reached: usb / can / dfu / linux / serial.
    connection: str
    #: service (running firmware) / ready (bootloader) / dfu / available / unknown.
    mode: str
    configured: bool = False
    version: str | None = None
    #: CAN application reported by Katapult (Klipper / Katapult / CanBoot).
    application: str | None = None
    #: CAN interface (e.g. can0) for CAN boards.
    interface: str | None = None


class BoardScan(BaseModel):
    """How many boards each discovery source contributed."""

    configured: int
    serial: int
    can: int
    dfu: int


class BoardDiscovery(BaseModel):
    """Every board detected on the host, with a per-source scan summary."""

    boards: list[Board]
    scanned: BoardScan
