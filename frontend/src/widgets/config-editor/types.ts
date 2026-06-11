/** Shapes returned by the backend Config Editor read routes (`/api/config/*`). */

export interface ConfigParamView {
  key: string
  value: string
  separator: string
  comment: string | null
}

export interface ConfigSectionView {
  header: string
  type: string
  name: string
  is_save_config: boolean
  params: ConfigParamView[]
}

export interface ConfigIssue {
  level: 'error' | 'warning'
  message: string
  section?: string
}

export interface ConfigFileView {
  filename: string
  raw: string
  sections: ConfigSectionView[]
  section_count: number
  issues: ConfigIssue[]
}

export interface ConfigFileInfo {
  path: string
  size: number | null
  modified: number | null
}

export interface ConfigFileList {
  files: ConfigFileInfo[]
}

export interface ConfigSaveResult {
  ok: boolean
  filename: string
  /** Path of the pre-save backup under `filamind-backups/`, or null for a brand-new file. */
  backup: string | null
  issues: ConfigIssue[]
  section_count: number
}

/** A param whose on-disk value differs from what Klipper is running. */
export interface ConfigDrift {
  section: string
  key: string
  disk: string
  live: string
}

/** Disk-vs-live comparison from `/api/config/drift`. */
export interface ConfigDriftResult {
  reachable: boolean
  save_config_pending: boolean
  pending_items: Record<string, unknown>
  warnings: string[]
  drifts: ConfigDrift[]
}

/** A whole-config pin-conflict finding (double-assigned pin / electronics caveat). */
export interface PinDoctorFinding {
  kind: string
  pin: string
  message: string
  sections: string[]
}

export interface PinDoctorMcu {
  name: string
  board_id: string | null
  board_name: string | null
  findings: PinDoctorFinding[]
}

export interface PinDoctorResult {
  reachable: boolean
  mcus: PinDoctorMcu[]
  total: number
}
