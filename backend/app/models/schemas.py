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
    #: Live telemetry from the MCU's ``last_stats`` (None when unavailable).
    freq: int | None = None
    #: Fraction of time the MCU was awake (0 to 1) — a rough load indicator.
    awake: float | None = None
    #: Retransmitted bytes — the key host↔MCU comms-health signal.
    retransmits: int | None = None


class HostMcu(BaseModel):
    """The optional Klipper 'Linux process' MCU running on the host (host GPIO/I2C/SPI).

    ``configured`` means an ``[mcu host]``-style section is wired into the running
    config (so it shows up as an active MCU); ``service_active`` means the host's
    ``klipper-mcu`` service is running, which can be true even when nothing uses it.
    """

    configured: bool = False
    service_active: bool = False
    #: Firmware version last flashed to the host MCU (from FilaMind's flash record).
    version: str | None = None


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
    #: Firmware version FilaMind last flashed to this board, if recorded.
    flashed_version: str | None = None


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


class ConfigChoice(BaseModel):
    """One selectable option of a Kconfig ``choice`` symbol."""

    name: str
    prompt: str


class ConfigNode(BaseModel):
    """A node of Klipper's Kconfig menu tree (menu, symbol, or choice)."""

    name: str
    #: menu / comment / bool / tristate / string / int / hex / choice / unknown.
    type: str
    prompt: str
    value: str | None = None
    help: str | None = None
    choices: list[ConfigChoice] = []
    readonly: bool = False
    children: list[ConfigNode] = []


class ConfigValue(BaseModel):
    """A single edited symbol value (name -> value)."""

    name: str
    value: str


class ConfigTreeRequest(BaseModel):
    """Request for the live Kconfig tree, with an optional base profile + edits."""

    profile: str | None = None
    values: list[ConfigValue] = []
    show_optional: bool = False


class ProfileSaveRequest(BaseModel):
    """Saves a set of Kconfig edits (atop an optional base) as a named profile."""

    name: str
    values: list[ConfigValue] = []
    base_profile: str | None = None


class FirmwareProfile(BaseModel):
    """A saved per-board firmware profile and the flags that shape its flashing."""

    name: str
    built: bool = False
    #: Klipper version this profile was last built with (from build_info.json).
    built_version: str | None = None
    is_can_bridge: bool = False
    is_linux: bool = False
    is_avr: bool = False


class ProfilesResponse(BaseModel):
    """Saved profiles plus whether the Kconfig editor is usable on this host."""

    kconfig_available: bool
    profiles: list[FirmwareProfile]


class FlashRequest(BaseModel):
    """A request to flash (or preview flashing) a board with a profile's firmware."""

    profile: str | None = None
    #: serial / can / dfu / make / linux.
    method: str
    #: Serial path, CAN UUID, DFU serial, or board id depending on the method.
    device: str
    interface: str = "can0"


class FlashPlan(BaseModel):
    """Read-only preview of what a flash would do, plus its safety gates."""

    method: str
    device: str
    artifact: str | None = None
    command: str
    offset: str
    printing: bool
    artifact_exists: bool
    sudo_ready: bool
    ready: bool
    warnings: list[str] = []
