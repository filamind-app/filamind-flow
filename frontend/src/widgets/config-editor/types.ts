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

/** Editability policy for one TMC register field (from `/api/drivers/field-policy/{model}`). */
export interface FieldPolicyEntry {
  risk: string
  control: 'number' | 'select' | 'toggle' | 'velocity' | string
  signed: boolean
  requires_confirm: boolean
  min?: number
  max?: number
  enum?: number[]
  velocity?: boolean
  note?: string
}

export interface FieldPolicyResponse {
  model: string
  fields: Record<string, FieldPolicyEntry>
}

/** One named pin of an MCU's resolved board (for pin-aware `*_pin` editing). */
export interface PinMapPin {
  pin: string
  owners: string[]
  caveat: string | null
}

export interface PinMapMcu {
  name: string
  board_name: string | null
  pins: PinMapPin[]
}

export interface PinMapResult {
  reachable: boolean
  mcus: PinMapMcu[]
}

/** One file node in the project include-dependency graph. */
export interface ConfigGraphNode {
  file: string
  sections: number
  includes: string[]
  missing: string[]
}

/** A cross-file lint finding (broken_include / orphan_driver / section_override). */
export interface ConfigGraphLint {
  level: 'error' | 'warning' | 'info'
  rule: string
  file: string
  message: string
  files?: string[]
}

export interface ConfigGraph {
  reachable: boolean
  /** Tree roots — the active config's root (so on-disk backups don't flood the include tree). */
  roots: string[]
  /** Files Klipper actually loads (the primary root + everything it includes, transitively). */
  active: string[]
  nodes: ConfigGraphNode[]
  lint: ConfigGraphLint[]
}

/** One project-wide search hit. */
export interface ConfigSearchMatch {
  file: string
  line: number
  text: string
}

export interface ConfigSearchResult {
  reachable: boolean
  query: string
  matches: ConfigSearchMatch[]
  truncated: boolean
}

/** One timestamped backup snapshot of a config file. */
export interface ConfigBackup {
  path: string
  flat: string
  stamp: string
  when: string
  size: number | null
  modified: number | null
}

export interface ConfigBackupList {
  reachable: boolean
  filename: string | null
  backups: ConfigBackup[]
}
