/** Write-path tests for the supervised vibrations run: start → poll → result, cancel
 *  surfacing as the CANCELLED sentinel, failure surfacing the task's last log line, and
 *  the reattach-after-reload contract (running task resumes, finished result collected,
 *  stale pointer cleared). All HTTP is mocked at the fetch boundary. */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  CANCELLED,
  cancelVibrations,
  reattachVibrations,
  runSupervisedVibrations,
  vibRun,
} from '../supervised'

const STORAGE_KEY = 'filamind-vibrations-task'

type Handler = (url: string, init?: RequestInit) => { status?: number; body?: unknown }

let handler: Handler

function jsonResponse(spec: { status?: number; body?: unknown }): Response {
  return new Response(JSON.stringify(spec.body ?? {}), {
    status: spec.status ?? 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

function task(over: Partial<Record<string, unknown>>): Record<string, unknown> {
  return {
    id: 't1',
    status: 'running',
    log: '',
    cancelled: false,
    progress: null,
    result: null,
    ...over,
  }
}

beforeEach(() => {
  vi.useFakeTimers()
  localStorage.clear()
  vibRun.taskId = null
  vibRun.status = 'idle'
  vibRun.progress = null
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL, init?: RequestInit) =>
      Promise.resolve(jsonResponse(handler(String(input), init))),
    ),
  )
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('runSupervisedVibrations', () => {
  it('starts, persists the task id, polls to the result, then cleans up', async () => {
    let polls = 0
    handler = (url) => {
      if (url.includes('/vibrations-profile/start')) return { body: { task_id: 't1' } }
      polls += 1
      if (polls === 1)
        return { body: task({ progress: { step: 2, total: 10, detail: { speed: 80 } } }) }
      return { body: task({ status: 'done', result: { verdict: 'ok', symmetry_pct: 95 } }) }
    }

    const run = runSupervisedVibrations({})
    await vi.advanceTimersByTimeAsync(0)
    expect(vibRun.status).toBe('running')
    expect(localStorage.getItem(STORAGE_KEY)).toBe('t1')

    await vi.advanceTimersByTimeAsync(1500)
    const result = await run
    expect(result.symmetry_pct).toBe(95)
    expect(vibRun.status).toBe('idle')
    expect(vibRun.taskId).toBeNull()
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull()
  })

  it('surfaces a cancelled task as the CANCELLED sentinel and resets state', async () => {
    handler = (url) => {
      if (url.includes('/start')) return { body: { task_id: 't1' } }
      if (url.endsWith('/cancel')) return { body: {} }
      return { body: task({ status: vibRun.status === 'cancelling' ? 'cancelled' : 'running' }) }
    }

    const run = runSupervisedVibrations({})
    run.catch(() => undefined) // assertions below; avoid an unhandled rejection window
    await vi.advanceTimersByTimeAsync(0)
    await cancelVibrations()
    expect(vibRun.status).toBe('cancelling')

    await vi.advanceTimersByTimeAsync(1500)
    await expect(run).rejects.toThrow(CANCELLED)
    expect(vibRun.status).toBe('idle')
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull()
  })

  it('surfaces a failed task via its last log line', async () => {
    handler = (url) => {
      if (url.includes('/start')) return { body: { task_id: 't1' } }
      return { body: task({ status: 'failed', log: '>>> sweep\n!! Heater fault\n' }) }
    }
    await expect(runSupervisedVibrations({})).rejects.toThrow('Heater fault')
    expect(vibRun.status).toBe('idle')
  })
})

describe('reattachVibrations', () => {
  it('returns null when nothing was tracked', async () => {
    handler = () => ({ body: {} })
    expect(await reattachVibrations()).toBeNull()
  })

  it('collects a finished result the dropped tab never saw', async () => {
    localStorage.setItem(STORAGE_KEY, 't9')
    handler = () => ({ body: task({ id: 't9', status: 'done', result: { symmetry_pct: 88 } }) })
    const result = await reattachVibrations()
    expect(result?.symmetry_pct).toBe(88)
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull()
  })

  it('clears a stale pointer when the task is unknown', async () => {
    localStorage.setItem(STORAGE_KEY, 'gone')
    handler = () => ({ status: 404, body: {} })
    expect(await reattachVibrations()).toBeNull()
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull()
  })

  it('resumes a still-running task to completion', async () => {
    localStorage.setItem(STORAGE_KEY, 't2')
    let polls = 0
    // Call 1 = reattach's own lookup, call 2 = the first poll — still running so the
    // resumed run is observable mid-flight; call 3 completes it.
    handler = () => {
      polls += 1
      if (polls <= 2) return { body: task({ id: 't2' }) }
      return { body: task({ id: 't2', status: 'done', result: { symmetry_pct: 91 } }) }
    }
    const run = reattachVibrations()
    await vi.advanceTimersByTimeAsync(0)
    expect(vibRun.status).toBe('running')
    await vi.advanceTimersByTimeAsync(1500)
    const result = await run
    expect(result?.symmetry_pct).toBe(91)
    expect(vibRun.status).toBe('idle')
  })
})
