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
