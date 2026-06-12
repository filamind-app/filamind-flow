/** Supervised max-flow run: start → poll → result, with shared reactive progress, cancel
 *  (the heater is always cut server-side), and reattach-after-reload. A minutes-long hot
 *  extrusion test is no longer a blind blocking POST. */
import { reactive } from 'vue'

import { i18n } from '@/core/i18n'
import { cancelTask, fetchTask, lastLogLine } from '@/core/tasks'

import { startMaxFlowTask } from './api'
import type { MaxFlowParams, MaxFlowResult } from './types'

const STORAGE_KEY = 'filamind-maxflow-task'
const POLL_MS = 1500

/** Thrown (as Error.message) when the run was cancelled — callers show it as info, not failure. */
export const CANCELLED = '__maxflow_cancelled__'

export const flowRun = reactive({
  taskId: null as string | null,
  status: 'idle' as 'idle' | 'running' | 'cancelling',
  progress: null as { step: number; total: number; detail?: Record<string, unknown> } | null,
})

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function pollToCompletion(taskId: string): Promise<MaxFlowResult> {
  for (;;) {
    const task = await fetchTask(taskId)
    if (task.progress) flowRun.progress = task.progress
    if (task.status === 'done' && task.result) return task.result as unknown as MaxFlowResult
    if (task.status === 'cancelled') throw new Error(CANCELLED)
    if (task.status !== 'running') {
      throw new Error(lastLogLine(task.log) || i18n.global.t('maxFlow.run.failed'))
    }
    await sleep(POLL_MS)
  }
}

function track(taskId: string): void {
  flowRun.taskId = taskId
  flowRun.status = 'running'
  flowRun.progress = null
  try {
    localStorage.setItem(STORAGE_KEY, taskId)
  } catch {
    /* best-effort */
  }
}

function untrack(): void {
  flowRun.taskId = null
  flowRun.status = 'idle'
  flowRun.progress = null
  try {
    localStorage.removeItem(STORAGE_KEY)
  } catch {
    /* ignore */
  }
}

export async function runSupervisedMaxFlow(params: MaxFlowParams): Promise<MaxFlowResult> {
  const taskId = await startMaxFlowTask(params)
  track(taskId)
  try {
    return await pollToCompletion(taskId)
  } finally {
    untrack()
  }
}

export async function cancelMaxFlow(): Promise<void> {
  if (!flowRun.taskId) return
  flowRun.status = 'cancelling'
  try {
    await cancelTask(flowRun.taskId)
  } catch {
    /* the poll loop surfaces the final state */
  }
}

/** After a reload: resume a running test or collect a finished result. Null when nothing. */
export async function reattachMaxFlow(): Promise<MaxFlowResult | null> {
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
    untrack()
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
  if (task.status === 'done' && task.result) return task.result as unknown as MaxFlowResult
  return null
}
