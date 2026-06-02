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
    #: True when this board is already saved in the registry.
    managed: bool = False


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
    #: The symbol's compiled-in default, shown as a hint in the editor.
    default: str | None = None
    #: Human-readable dependency expression (why a symbol is gated), if any.
    dep_str: str | None = None
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


class ProfileRenameRequest(BaseModel):
    """Renames or duplicates a profile to ``new_name``."""

    new_name: str


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
    #: Whether the board carries a Katapult bootloader (drives the reboot step).
    is_katapult: bool = True


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


class ExternalFirmware(BaseModel):
    """A registered external firmware file and its editable flash properties."""

    name: str
    label: str
    method: str = "serial"
    offset: str = ""
    interface: str = "can0"
    notes: str = ""
    filename: str | None = None
    size: int = 0
    #: Read-only properties detected inside the binary (best-effort).
    detected_version: str | None = None
    detected_mcu: str | None = None
    #: The firmware's app ("Klipper" / "Katapult") and its baked-in build config.
    detected_app: str | None = None
    detected_config: dict[str, str] | None = None


class ExternalFirmwareResponse(BaseModel):
    """All registered external firmware files."""

    firmware: list[ExternalFirmware] = []


class ExternalMetaUpdate(BaseModel):
    """A patch of an external firmware's editable properties (only set fields apply)."""

    label: str | None = None
    method: str | None = None
    offset: str | None = None
    interface: str | None = None
    notes: str | None = None


class ExternalFlashRequest(BaseModel):
    """Flashes a registered external firmware file onto a board."""

    device: str
    is_katapult: bool = True


class DeviceBase(BaseModel):
    """The editable settings of a board saved in the registry."""

    id: str
    name: str
    #: Build profile assigned to this board (None until one is chosen).
    profile: str | None = None
    #: How the board is flashed: serial / can / dfu / linux / beacon.
    method: str = "serial"
    interface: str = "can0"
    baudrate: int = 250000
    notes: str = ""
    is_katapult: bool = True
    is_bridge: bool = False
    #: Bootloader identities the board takes on under Katapult / DFU, if distinct.
    serial_id: str | None = None
    dfu_id: str | None = None
    #: Skip this board during batch (Flash All) flashes.
    exclude_from_batch: bool = False
    #: Overrides ``make`` for this board's build, when set.
    custom_make_command: str | None = None


class Device(DeviceBase):
    """A device as returned to the UI, enriched with its flash history."""

    #: Read back from the flash records (not stored in devices.json).
    flashed_version: str | None = None
    flashed_commit: str | None = None
    last_flashed: str | None = None


class DeviceSave(DeviceBase):
    """Upsert payload for a device, with an optional previous id (rename)."""

    old_id: str | None = None


class AttachRequest(BaseModel):
    """Binds a discovered bootloader identity to an existing device."""

    device_id: str
    hardware_id: str
    #: Which identity to set: serial / dfu.
    kind: str


class DevicesResponse(BaseModel):
    """The saved devices."""

    devices: list[Device]


class BatchRequest(BaseModel):
    """Starts a batch run over the registry: build / flash / flash-ready."""

    #: build-all / flash-all / flash-ready / build-flash-all.
    action: str


class TaskStatus(BaseModel):
    """A background batch task's accumulating log and status."""

    id: str
    #: running / done / cancelled / failed.
    status: str
    log: str
    cancelled: bool


class ServiceInfo(BaseModel):
    """A Klipper / Moonraker systemd unit and whether it is currently active."""

    name: str
    active: bool


class ServicesResponse(BaseModel):
    """The host's firmware-related services."""

    services: list[ServiceInfo]


class ServiceResult(BaseModel):
    """Outcome of a start/stop/restart on one service."""

    name: str
    ok: bool


class ServiceActionResponse(BaseModel):
    """Per-service results of a services action."""

    results: list[ServiceResult]


class RebootRequest(BaseModel):
    """Asks a board to reboot into a bootloader."""

    #: serial / can.
    method: str
    device: str
    interface: str = "can0"
    #: katapult (flashtool -r) / dfu (1200-baud magic-baud touch).
    mode: str = "katapult"


class BeaconProbe(BaseModel):
    """A connected Beacon eddy-current probe."""

    id: str
    name: str
    revision: str
    serial: str


class BeaconResponse(BaseModel):
    """Discovered Beacon probes plus the plugin path and available version."""

    probes: list[BeaconProbe]
    repo: str | None = None
    available_version: str | None = None


class BeaconFlashRequest(BaseModel):
    """Updates a Beacon probe's firmware."""

    device: str


class BackupImportResponse(BaseModel):
    """What a restore put back."""

    restored_devices: bool
    restored_profiles: list[str]


class HealthCheck(BaseModel):
    """One install-integrity check and how to fix it."""

    name: str
    ok: bool
    detail: str


class HealthReport(BaseModel):
    """Whether the host is set up for flashing, with per-check detail."""

    healthy: bool
    checks: list[HealthCheck]


class ShaperResult(BaseModel):
    """One shaper family's fitted result on the resonance data."""

    name: str
    freq: float
    #: Estimated remaining vibrations, as a percentage (lower is better).
    vibrations_pct: float
    smoothing: float
    #: Suggested max_accel (mm/s^2) to avoid excessive smoothing.
    max_accel: float
    recommended: bool = False


class ShaperCurve(BaseModel):
    """A shaper's vibration-reduction curve, sampled over the frequency bins."""

    name: str
    vals: list[float]


class ShaperAnalysis(BaseModel):
    """Result of analysing a resonance CSV with Klipper's input-shaper calibration."""

    recommended_shaper: str | None = None
    recommended_freq: float | None = None
    #: The axis this CSV belongs to (x / y), if the caller supplied it.
    axis: str | None = None
    max_freq: float
    shapers: list[ShaperResult] = []
    #: Frequency bins (Hz) shared by every PSD + shaper-curve series below.
    freqs: list[float] = []
    psd_x: list[float] = []
    psd_y: list[float] = []
    psd_z: list[float] = []
    psd_sum: list[float] = []
    shaper_curves: list[ShaperCurve] = []
    #: Human-readable calibration log lines (one per fitted shaper).
    log: list[str] = []
    #: Filename this analysis came from (set when imported from the printer host).
    source_file: str | None = None


class ResonanceFile(BaseModel):
    """A resonance CSV Klipper wrote on the printer host."""

    name: str
    path: str
    size: int
    #: Last-modified time (epoch seconds).
    mtime: float
    #: Axis guessed from the filename (x / y), if any.
    axis: str | None = None


class ResonanceFilesResponse(BaseModel):
    """Resonance CSVs discovered on the host, plus the directories scanned."""

    files: list[ResonanceFile] = []
    dirs: list[str] = []


class NoiseChip(BaseModel):
    """One accelerometer chip's idle noise — the mean PSD per axis."""

    #: The chip's mounting-axis label as Klipper reports it (e.g. "xy").
    label: str
    x: float
    y: float
    z: float


class NoiseResult(BaseModel):
    """Result of ``MEASURE_AXES_NOISE`` — the accelerometer's idle noise floor.

    Validates the sensor mount before a resonance test. Per Klipper's guidance,
    ~1-100 is normal; values of ~1000+ indicate a problem.
    """

    chips: list[NoiseChip] = []
    #: Largest noise value across all chips / axes.
    max_noise: float
    #: "good" (<100), "elevated" (100-1000), "high" (>=1000).
    grade: str
    ok: bool
    threshold: float


class BeltComparison(BaseModel):
    """Two belt-direction resonance captures for a CoreXY belt-tension comparison."""

    #: Excited along the (1,1) diagonal.
    belt_a: ShaperAnalysis
    #: Excited along the (1,-1) diagonal.
    belt_b: ShaperAnalysis


class AxisMapping(BaseModel):
    """One machine axis → accelerometer axis mapping from axes-map detection."""

    machine_axis: str
    accel_axis: str
    #: "+" or "-".
    sign: str
    angle_error: float
    confidence: float
    #: True if this axis was reconstructed (2-axis / bed-slinger machine).
    extrapolated: bool


class VelocitySeries(BaseModel):
    """Downsampled integrated-velocity series for one machine-axis stroke (for the plot)."""

    axis: str
    t: list[float] = []
    vx: list[float] = []
    vy: list[float] = []
    vz: list[float] = []
    detected_axis: str
    confidence: float
    extrapolated: bool


class AxesMapResult(BaseModel):
    """Result of axes-map calibration — the accelerometer's detected orientation."""

    #: The detected Klipper ``axes_map`` string, e.g. "-z, y, x".
    axes_map: str
    #: The accelerometer config section the axes_map goes in (e.g. "adxl345").
    chip: str = "adxl345"
    #: ok | warning | error.
    status: str
    messages: list[str] = []
    mappings: list[AxisMapping] = []
    #: Intrinsic-XYZ Euler tilt angles (deg), keyed x/y/z.
    euler: dict[str, float] = {}
    #: Gravity magnitude (m/s²).
    gravity: float
    #: Dynamic noise (mm/s²).
    noise: float
    #: ok | warning | error.
    noise_grade: str
    current_axes_map: str | None = None
    matches_current: bool | None = None
    accel: float
    extrapolated_axis: int | None = None
    velocity_series: list[VelocitySeries] = []
    source_files: list[str] = []
