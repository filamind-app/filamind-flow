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
  tools: FirmwareTools
}
