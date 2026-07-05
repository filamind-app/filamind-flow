/** Shapes returned by `GET /api/doctor/scan`. */

export interface DoctorLink {
  kind: 'config_section' | 'config_file' | 'stepper' | 'topology_node' | 'widget' | string
  value: string
  tab?: string
}

export interface DoctorFinding {
  /** Stable code translated on the frontend (`machineDoctor.finding.<code>`). */
  code: string
  level: 'error' | 'warning' | 'info' | string
  params: Record<string, string | number | null>
  link: DoctorLink | null
}

export interface DoctorCategory {
  key: string
  status: 'ok' | 'warn' | 'fail' | 'unknown' | string
  errors: number
  warnings: number
  findings: DoctorFinding[]
}

/** One weighted contributor to the composite grade (score null = "not measured").
 *  `reason` explains a null score: `undone` = a Get-Started task never run (input shaping, max
 *  flow) - shown as a "todo" bar and held out of the number; `blocked` = can't judge right now
 *  (Moonraker/host down); `measured` = the score is real. */
export interface DoctorPillar {
  key: string
  score: number | null
  weight: number
  status: 'ok' | 'warn' | 'fail' | 'unknown' | 'todo' | string
  detail: Record<string, number | string | null>
  reason?: 'measured' | 'undone' | 'blocked' | string
}

/** Translatable verdict: `machineDoctor.assessment.<code>`; params name the weakest pillar, or -
 *  for `setup_incomplete` - the array of undone setup pillar keys (localized on the frontend). */
export interface DoctorAssessment {
  code: string
  params: Record<string, string | number | string[] | null>
}

export interface DoctorService {
  name: string
  active: boolean
  sub_state?: string | null
}

export interface DoctorServices {
  source: 'moonraker' | 'systemd' | null | string
  units: DoctorService[]
}

export interface DoctorStatAxis {
  axis: string
  shaper?: string | null
  freq?: number | null
  grade?: string | null
}

export interface DoctorStats {
  max_flow: {
    at?: string
    max_flow_mm3s?: number | null
    recommend?: { conservative?: number | null; balanced?: number | null } | null
    method?: string | null
    hotend?: string | null
    expected_max_flow_mm3s?: number | null
  } | null
  tuning: DoctorStatAxis[] | null
  firmware: {
    host_version?: string | null
    out_of_sync?: number | null
    mcu_count?: number | null
  } | null
}

export interface DoctorReport {
  grade: string
  score: number
  errors: number
  warnings: number
  categories: DoctorCategory[]
  pillars: DoctorPillar[]
  assessment: DoctorAssessment
  services: DoctorServices
  stats: DoctorStats
  /** How many Get-Started setup steps (input shaping, max flow, motor drivers) are done, and which
   *  remain. Undone steps count as 0 in the score, so `pending` is what's dragging it down. */
  setup: { done: number; total: number; pending: string[] }
}
