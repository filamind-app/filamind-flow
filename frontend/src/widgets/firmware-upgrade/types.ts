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
}

/** The optional Klipper "Linux process" MCU running on the host machine. */
export interface HostMcu {
  /** An `[mcu host]`-style section is wired into the running config. */
  configured: boolean
  /** The host's `klipper-mcu` service is running (can be idle if not configured). */
  service_active: boolean
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
  is_can_bridge: boolean
  is_linux: boolean
  is_avr: boolean
}

export interface ProfilesResponse {
  kconfig_available: boolean
  profiles: FirmwareProfile[]
}
