/** Shapes returned by the Host Control backend (`/api/host/*`). Phase 1 is the read-only monitor;
 *  later phases add services, disk cleanup and the system-changing actions.
 */

export interface HostBlock {
  hostname: string
  distro: string
  kernel: string
  arch: string
  uptime_s: number | null
}

export interface CpuBlock {
  temp_c: number | null
  load: number[] | null
  cores: number | null
}

export interface MemoryBlock {
  total_kb: number
  available_kb: number
  used_kb: number
  swap_total_kb: number
  swap_used_kb: number
}

export interface DiskBlock {
  label: string
  path: string
  total: number
  used: number
  free: number
  pct: number
}

export interface ThrottleBlock {
  supported: boolean
  value: number | null
  undervoltage: boolean | null
  flags: string[]
}

export interface ProcessBlock {
  pid: number
  cpu: number
  mem: number
  command: string
}

export interface NetworkBlock {
  iface: string
  ip: string
  ssid: string
  signal: number | null
}

export interface TimeBlock {
  now: string
  timezone: string
  ntp_enabled: boolean
  ntp_synced: boolean
  rtc: string
}

export interface LocaleBlock {
  lang: string
  keymap: string
}

export interface HostMonitor {
  host: HostBlock
  cpu: CpuBlock
  memory: MemoryBlock
  disk: DiskBlock[]
  throttle: ThrottleBlock
  processes: ProcessBlock[]
  network: NetworkBlock
  time: TimeBlock
  locale: LocaleBlock
}

// ── Services (Phase 2) ─────────────────────────────────────────────────────────

export interface ServiceUnit {
  name: string
  load_state: string
  active: boolean
  active_state: string
  sub_state: string
  description: string
  enabled: string
  critical: boolean
  protected: boolean
}

export interface ServiceDetail {
  name: string
  description: string
  load_state: string
  active_state: string
  sub_state: string
  enabled: string
  fragment_path: string
  can_delete: boolean
  critical: boolean
  protected: boolean
}

export interface ServiceActionResult {
  name: string
  action?: string
  ok: boolean
  refused: boolean
  output: string
  needs_setup?: boolean
}

export type ServiceAction = 'start' | 'stop' | 'restart' | 'enable' | 'disable' | 'mask' | 'unmask'

// ── Disk cleanup (Phase 3) ─────────────────────────────────────────────────────

export interface CleanupTarget {
  id: string
  bytes: number
  count: number
  available: boolean
}

export interface CleanupResult {
  id: string
  freed_bytes: number
  removed: number
  ok: boolean
  needs_setup?: boolean
}

export interface CleanupRunResult {
  results: CleanupResult[]
  freed_bytes: number
}

// ── System settings (Phase 4) ──────────────────────────────────────────────────

export interface NetworkConfig {
  available: boolean
  configurable: boolean
  device: string
  connection: string
  type: string
  method: string // 'auto' | 'manual' | ''
  address: string
  cidr: number | null
  gateway: string
  dns: string[]
}

export interface SystemInfo {
  timezone: string
  ntp_enabled: boolean
  ntp_synced: boolean
  timezones: string[]
  lang: string
  keymap: string
  locales: string[]
  keymaps: string[]
  hostname: string
  network: NetworkConfig
}

export interface SystemActionResult {
  ok: boolean
  refused: boolean
  output: string
  needs_setup?: boolean
}

export type PowerAction = 'reboot' | 'shutdown'

export interface NetworkSetReq {
  method: 'auto' | 'manual'
  address?: string
  cidr?: number | null
  gateway?: string
  dns?: string
}
