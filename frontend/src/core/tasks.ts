import { resolveEndpoints } from '@/core/moonraker'

/** A supervised background task's polled state (mirrors the backend TaskStatus). */
export interface SupervisedTask {
  id: string
  status: 'running' | 'done' | 'cancelled' | 'failed' | string
  log: string
  cancelled: boolean
  progress: { step: number; total: number; detail?: Record<string, unknown> } | null
  result: Record<string, unknown> | null
}

export async function fetchTask(id: string): Promise<SupervisedTask> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/tasks/${encodeURIComponent(id)}`)
  if (!response.ok) throw new Error(`Task lookup failed (${response.status})`)
  return (await response.json()) as SupervisedTask
}

export async function cancelTask(id: string): Promise<void> {
  const { backendUrl } = resolveEndpoints()
  const response = await fetch(`${backendUrl}/api/tasks/${encodeURIComponent(id)}/cancel`, {
    method: 'POST',
  })
  if (!response.ok) throw new Error(`Cancel failed (${response.status})`)
}

/** The last non-empty log line — the human-facing error a failed task left behind. */
export function lastLogLine(log: string): string {
  const lines = log.split('\n').filter((l) => l.trim())
  return lines.length ? lines[lines.length - 1].replace(/^!+\s*/, '') : ''
}
