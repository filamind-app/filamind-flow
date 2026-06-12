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

export interface DoctorReport {
  grade: string
  score: number
  errors: number
  warnings: number
  categories: DoctorCategory[]
}
