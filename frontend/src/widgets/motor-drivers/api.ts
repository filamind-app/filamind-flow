import { resolveEndpoints } from '@/core/moonraker'

import type {
  ApplyRequest,
  ApplyResponse,
  ConfigBlockRequest,
  DriverRecommendation,
  DriversStatus,
  MotorCatalog,
  RecommendRequest,
} from './types'

/** Fetches the read-only TMC driver inventory from the FilaMind backend. */
export async function fetchDriverStatus(): Promise<DriversStatus> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/drivers/status`)
  if (!response.ok) {
    throw new Error(`Driver status request failed (${response.status})`)
  }
  return (await response.json()) as DriversStatus
}

/** Fetches the stepper-motor catalog (datasheet parameters) for the motor picker. */
export async function fetchMotorCatalog(): Promise<MotorCatalog> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/drivers/motors`)
  if (!response.ok) {
    throw new Error(`Motor catalog request failed (${response.status})`)
  }
  return (await response.json()) as MotorCatalog
}

/** Assigns a catalogued motor to a stepper (pass null to clear the assignment). */
export async function saveMotorAssignment(
  stepper: string,
  motorModel: string | null,
): Promise<void> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/drivers/mapping`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ stepper, motor_model: motorModel }),
  })
  if (!response.ok) {
    throw new Error(`Motor assignment failed (${response.status})`)
  }
}

/** Computes a driver-tuning recommendation for a motor (compute-only). */
export async function fetchRecommendation(req: RecommendRequest): Promise<DriverRecommendation> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/drivers/recommend`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!response.ok) {
    const detail = await response
      .json()
      .then((b) => b?.detail)
      .catch(() => null)
    throw new Error(detail || `Recommendation failed (${response.status})`)
  }
  return (await response.json()) as DriverRecommendation
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    throw new Error(`Request failed (${response.status})`)
  }
  return (await response.json()) as T
}

/** Renders a printer.cfg override block to copy (no write). */
export async function fetchConfigBlock(body: ConfigBlockRequest): Promise<{ text: string }> {
  return postJson('/api/drivers/config-block', body)
}

/** Writes tuning to a driver now (gated server-side; refuses while printing). */
export async function applyTuning(body: ApplyRequest): Promise<ApplyResponse> {
  return postJson('/api/drivers/apply', body)
}

/** INIT_TMC — re-apply the stepper's configured registers (undo a live apply). */
export async function revertDriver(stepper: string): Promise<ApplyResponse> {
  return postJson('/api/drivers/init', { stepper })
}

/** Drive AUTOTUNE_TMC if the klipper_tmc_autotune extra is installed for this stepper. */
export async function runAutotune(stepper: string): Promise<ApplyResponse> {
  return postJson('/api/drivers/autotune', { stepper })
}
