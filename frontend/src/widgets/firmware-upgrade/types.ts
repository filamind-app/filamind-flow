/** Mirrors the backend `FirmwareStatus` schema (GET /api/firmware/status). */

export interface HostFirmware {
  version: string | null
  state: string | null
}

export interface McuFirmware {
  name: string
  version: string | null
  /** True if the MCU version matches the host, false on mismatch, null if unknown. */
  in_sync: boolean | null
  /** Connection type from the Klipper config: host / canbus / usb / serial. */
  kind: string
  /** Live telemetry from the MCU's last_stats (null when unavailable). */
  freq: number | null
  awake: number | null
  retransmits: number | null
}

/** The optional Klipper "Linux process" MCU running on the host machine. */
export interface HostMcu {
  /** An `[mcu host]`-style section is wired into the running config. */
  configured: boolean
  /** The host's `klipper-mcu` service is running (can be idle if not configured). */
  service_active: boolean
  /** Firmware version FilaMind last flashed to the host MCU (null if never). */
  version: string | null
}

export interface FirmwareTools {
  klipper: boolean
  katapult: boolean
  flashtool: boolean
  dfu_util: boolean
  avrdude: boolean
  can_utils: boolean
}

export interface FirmwareStatus {
  reachable: boolean
  host: HostFirmware
  mcus: McuFirmware[]
  host_mcu: HostMcu
  tools: FirmwareTools
}

/** A discovered board, merged across Moonraker + USB/CAN/DFU scans. */
export interface Board {
  id: string
  name: string
  mcu_name: string | null
  /** usb / can / dfu / linux / serial. */
  connection: string
  /** service (running) / ready (bootloader) / dfu / available / unknown. */
  mode: string
  configured: boolean
  version: string | null
  application: string | null
  interface: string | null
  /** Firmware version FilaMind last flashed to this board, if recorded. */
  flashed_version: string | null
  /** True when this board is already saved in the registry. */
  managed: boolean
}

export interface BoardScan {
  configured: number
  serial: number
  can: number
  dfu: number
}

export interface BoardDiscovery {
  boards: Board[]
  scanned: BoardScan
}

/** One option of a Kconfig `choice` symbol. */
export interface ConfigChoice {
  name: string
  prompt: string
}

/** A node of Klipper's Kconfig menu tree (menu, symbol, or choice). */
export interface ConfigNode {
  name: string
  type: string
  prompt: string
  value: string | null
  help: string | null
  choices: ConfigChoice[]
  readonly: boolean
  children: ConfigNode[]
}

/** A single edited symbol value sent back to the backend. */
export interface ConfigEdit {
  name: string
  value: string
}

export interface FirmwareProfile {
  name: string
  built: boolean
  /** Klipper version this profile was last built with (null if never). */
  built_version: string | null
  is_can_bridge: boolean
  is_linux: boolean
  is_avr: boolean
}

export interface ProfilesResponse {
  kconfig_available: boolean
  profiles: FirmwareProfile[]
}

/** A request to flash (or preview flashing) a board. */
export interface FlashRequest {
  profile: string | null
  method: string
  device: string
  interface: string
}

/** Read-only preview of what a flash would do, plus its safety gates. */
export interface FlashPlan {
  method: string
  device: string
  artifact: string | null
  command: string
  offset: string
  printing: boolean
  artifact_exists: boolean
  sudo_ready: boolean
  ready: boolean
  warnings: string[]
}

/** A board saved in your devices: which profile it runs and how to flash it. */
export interface Device {
  id: string
  name: string
  profile: string | null
  /** serial / can / dfu / linux / beacon. */
  method: string
  interface: string
  baudrate: number
  notes: string
  is_katapult: boolean
  is_bridge: boolean
  /** Bootloader identities the board takes on under Katapult / DFU, if distinct. */
  serial_id: string | null
  dfu_id: string | null
  exclude_from_batch: boolean
  custom_make_command: string | null
  /** Read back from the flash records (not stored in devices.json). */
  flashed_version: string | null
  flashed_commit: string | null
  last_flashed: string | null
}

/** Upsert payload for a device, with an optional previous id (rename). */
export interface DeviceSave extends Partial<Device> {
  id: string
  name: string
  old_id?: string | null
}

/** The saved devices, as returned by the backend. */
export interface DevicesResponse {
  devices: Device[]
}

/** A background batch task's accumulating log and status. */
export interface TaskStatus {
  id: string
  /** running / done / cancelled / failed. */
  status: string
  log: string
  cancelled: boolean
}

/** A Klipper / Moonraker systemd service and whether it is active. */
export interface ServiceInfo {
  name: string
  active: boolean
}

export interface ServicesResponse {
  services: ServiceInfo[]
}

/** A connected Beacon eddy-current probe. */
export interface BeaconProbe {
  id: string
  name: string
  revision: string
  serial: string
}

export interface BeaconResponse {
  probes: BeaconProbe[]
  repo: string | null
  available_version: string | null
}

/** One install-integrity check and how to fix it. */
export interface HealthCheck {
  name: string
  ok: boolean
  detail: string
}

export interface HealthReport {
  healthy: boolean
  checks: HealthCheck[]
}
