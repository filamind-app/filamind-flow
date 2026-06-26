import { beforeEach, describe, expect, it, vi } from 'vitest'

// resolveEndpoints reads window/config; stub it so the probe URL is deterministic.
vi.mock('@/core/moonraker', () => ({ resolveEndpoints: () => ({ backendUrl: 'http://x' }) }))

// Fresh module (and its module-level `threeDInstalled` ref) per test.
beforeEach(() => {
  vi.resetModules()
})
const load = () => import('@/core/host/suite')

const okFetch = (body: unknown): typeof fetch =>
  (() =>
    Promise.resolve({ ok: true, json: () => Promise.resolve(body) })) as unknown as typeof fetch

describe('suite host detection (R6 runtime gate)', () => {
  it('starts locked and unlocks when FilaMind 3D is installed', async () => {
    const { detectSuiteHost, suiteUnlocked } = await load()
    expect(suiteUnlocked.value).toBe(false)
    await detectSuiteHost(okFetch({ status: { 'filamind-3d': { status: 'installed' } } }))
    expect(suiteUnlocked.value).toBe(true)
  })

  it('stays locked when FilaMind 3D is not installed', async () => {
    const { detectSuiteHost, suiteUnlocked } = await load()
    await detectSuiteHost(okFetch({ status: { 'filamind-3d': { status: 'not-installed' } } }))
    expect(suiteUnlocked.value).toBe(false)
  })

  it('stays locked on a non-200 response', async () => {
    const { detectSuiteHost, suiteUnlocked } = await load()
    const bad = (() => Promise.resolve({ ok: false })) as unknown as typeof fetch
    await detectSuiteHost(bad)
    expect(suiteUnlocked.value).toBe(false)
  })

  it('never throws when the probe rejects (stays locked)', async () => {
    const { detectSuiteHost, suiteUnlocked } = await load()
    const boom = (() => Promise.reject(new Error('offline'))) as unknown as typeof fetch
    await expect(detectSuiteHost(boom)).resolves.toBeUndefined()
    expect(suiteUnlocked.value).toBe(false)
  })
})
