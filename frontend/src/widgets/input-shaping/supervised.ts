/** Supervised vibrations-profile run: start → poll → result, with shared reactive progress,
 *  cancel, and reattach-after-reload. The minutes-long sweep is no longer a blind blocking POST —
 *  the task id is persisted so a dropped tab can pick the run (or its finished result) back up. */
import { reactive } from 'vue'

import { i18n } from '@/core/i18n'
import { resolveEndpoints } from '@/core/moonraker'
import { cancelTask, fetchTask, lastLogLine } from '@/core/tasks'

import type { VibrationsOptions } from './api'
import type { VibrationsProfile } from './types'

const STORAGE_KEY = 'filamind-vibrations-task'
const POLL_MS = 1500

/** Thrown (as Error.message) when the run was cancelled — callers show it as info, not failure. */
export const CANCELLED = '__vibrations_cancelled__'

export const vibRun = reactive({
  taskId: null as string | null,
  status: 'idle' as 'idle' | 'running' | 'cancelling',
  progress: null as { step: number; total: number; detail?: Record<string, unknown> } | null,
})

async function startTask(opts: VibrationsOptions): Promise<string> {
  const { backendUrl } = resolveEndpoints()
  const params = new URLSearchParams()
  if (opts.maxSpeed != null) params.set('max_speed', String(opts.maxSpeed))
  if (opts.minSpeed != null) params.set('min_speed', String(opts.minSpeed))
  if (opts.speedIncrement != null) params.set('speed_increment', String(opts.speedIncrement))
  if (opts.size != null) params.set('size', String(opts.size))
  if (opts.accel != null) params.set('accel', String(opts.accel))
  const query = params.toString()
  const response = await fetch(
    `${backendUrl}/api/shaper/vibrations-profile/start${query ? `?${query}` : ''}`,
    { method: 'POST' },
  )
  if (!response.ok) throw new Error(`Vibrations profile failed to start (${response.status})`)
  return ((await response.json()) as { task_id: string }).task_id
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function pollToCompletion(taskId: string): Promise<VibrationsProfile> {
  for (;;) {
    const task = await fetchTask(taskId)
    if (task.progress) vibRun.progress = task.progress
    if (task.status === 'done' && task.result) return task.result as unknown as VibrationsProfile
    if (task.status === 'cancelled') throw new Error(CANCELLED)
    if (task.status !== 'running') {
      const detail = lastLogLine(task.log)
      throw new Error(detail || i18n.global.t('inputShaping.fromPrinter.errVibrationsProfile'))
    }
    await sleep(POLL_MS)
  }
}

function track(taskId: string): void {
  vibRun.taskId = taskId
  vibRun.status = 'running'
  vibRun.progress = null
  try {
    localStorage.setItem(STORAGE_KEY, taskId)
  } catch {
    /* persistence is best-effort */
  }
}

function untrack(): void {
  vibRun.taskId = null
  vibRun.status = 'idle'
  vibRun.progress = null
  try {
    localStorage.removeItem(STORAGE_KEY)
  } catch {
    /* ignore */
  }
}

/** Run the sweep supervised (same signature/result as the old blocking call). */
export async function runSupervisedVibrations(
  opts: VibrationsOptions = {},
): Promise<VibrationsProfile> {
  const taskId = await startTask(opts)
  track(taskId)
  try {
    return await pollToCompletion(taskId)
  } finally {
    untrack()
  }
}

/** Flag the running sweep to stop at its next checkpoint (cleanup always runs server-side). */
export async function cancelVibrations(): Promise<void> {
  if (!vibRun.taskId) return
  vibRun.status = 'cancelling'
  try {
    await cancelTask(vibRun.taskId)
  } catch {
    /* the poll loop will surface the final state either way */
  }
}

/** After a reload: pick a still-running sweep back up (resolves with its result), or collect a
 *  finished result the dropped tab never saw. Returns null when there is nothing to reattach. */
export async function reattachVibrations(): Promise<VibrationsProfile | null> {
  let stored: string | null = null
  try {
    stored = localStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
  if (!stored) return null
  let task
  try {
    task = await fetchTask(stored)
  } catch {
    untrack() // unknown/expired task — clear the stale pointer
    return null
  }
  if (task.status === 'running') {
    track(stored)
    try {
      return await pollToCompletion(stored)
    } finally {
      untrack()
    }
  }
  untrack()
  if (task.status === 'done' && task.result) return task.result as unknown as VibrationsProfile
  return null
}
