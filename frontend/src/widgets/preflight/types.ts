/** One pre-print readiness check (mirrors the backend; rendered via `preflight.checks.<code>`). */
export interface PreflightCheck {
  code: string
  ok: boolean
  /** 'error' = hard blocker, 'warn' = informational. */
  level: string
  params: Record<string, unknown>
}

export interface PreflightResult {
  ready: boolean
  checks: PreflightCheck[]
}
