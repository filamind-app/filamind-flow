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

/** One weighted contributor to the composite grade (score null = "not measured"). */
export interface DoctorPillar {
  key: string
  score: number | null
  weight: number
  status: 'ok' | 'warn' | 'fail' | 'unknown' | string
  detail: Record<string, number | string | null>
}

/** Translatable verdict: `machineDoctor.assessment.<code>`; params name the weakest pillar. */
export interface DoctorAssessment {
  code: string
  params: Record<string, string | number | null>
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
}
