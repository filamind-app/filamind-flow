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

/** Read-only boot configuration (the Boot panel). */
export interface BootInfo {
  /** systemd default target, e.g. "graphical.target" / "multi-user.target". */
  default_target: string | null
  /** Whether the host boots into a graphical session. */
  graphical: boolean
  /** The active boot-splash image (path + byte size), or null when none is found. */
  splash: { path: string; size: number } | null
  /** The active plymouth theme, when plymouth is present. */
  plymouth_theme: string | null
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

// -- Services (Phase 2) ---------------------------------------------------------

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

// -- Disk cleanup (Phase 3) -----------------------------------------------------

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

// -- System settings (Phase 4) --------------------------------------------------

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

// -- CAN bus control (Phase 5) --------------------------------------------------

/** One host SocketCAN interface with its live status + best-effort bridging-adapter link. */
export interface CanBusStatus {
  interface: string
  driver: string | null
  bitrate: number | null
  /** IFF_UP flag: true=up, false=down, null=couldn't read (no `ip`). */
  link_up: boolean | null
  /** CAN controller state: ERROR-ACTIVE (healthy) / ERROR-PASSIVE / BUS-OFF / STOPPED. */
  state: string | null
  /** CAN bus error counters (berr-counter), null when unavailable. */
  errors_rx: number | null
  errors_tx: number | null
  txqueuelen: number | null
  /** Catalog link to the bridging USB-CAN adapter, if external (shared with Board Topology). */
  board_id?: string | null
  board_match?: 'suggested' | 'confirmed' | null
  board_match_confidence?: number
  /** Current tunable values (bit timing, recovery, CAN-FD, control-mode flags). */
  params?: CanParams
  /** The controller's reported ranges + which extras it supports (drive the form bounds). */
  limits?: CanLimits
}

/** Live CAN tunables (only the ones the controller reports are present). */
export interface CanParams {
  sample_point?: number
  sjw?: number
  brp?: number
  tq?: number
  prop_seg?: number
  phase_seg1?: number
  phase_seg2?: number
  restart_ms?: number
  dbitrate?: number
  dsample_point?: number
  /** Active control modes, keyed by api name (listen_only, loopback, triple_sampling, …). */
  flags?: Record<string, boolean>
}

export interface CanLimits {
  tseg1_min?: number
  tseg1_max?: number
  tseg2_min?: number
  tseg2_max?: number
  sjw_max?: number
  brp_min?: number
  brp_max?: number
  clock_freq?: number
  fd_supported?: boolean
}

/** Outcome of a CAN link/bitrate change (mirrors the host service-action result shape). */
export interface CanBusActionResult {
  interface: string
  ok: boolean
  refused: boolean
  output: string
  needs_setup?: boolean
  /** Set when the action also requested a Klipper FIRMWARE_RESTART: did the restart succeed? */
  restarted?: boolean
}

// -- Health advisor (Phase 6) ---------------------------------------------------

/** One graded host-health card (CPU / memory / disk / clock / services). */
export interface HealthCard {
  id: string
  status: 'ok' | 'warn' | 'fail' | 'unknown'
  /** 0-100. */
  score: number
  /** Letter grade derived from the score (A-F). */
  grade: string
  /** Badge codes (rendered via hostControl.advisor.badge.<code>). */
  badges: string[]
  /** Backend-built detail line (numbers + units). */
  detail: string
  /** i18n suffix for an actionable fix hint, or null. */
  fix_code: string | null
}

export interface HealthAdvisory {
  cards: HealthCard[]
}

export interface NetworkSetReq {
  method: 'auto' | 'manual'
  address?: string
  cidr?: number | null
  gateway?: string
  dns?: string
}
