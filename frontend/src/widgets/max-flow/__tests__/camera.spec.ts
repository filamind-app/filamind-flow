import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/core/moonraker', () => ({
  resolveEndpoints: () => ({
    httpUrl: 'http://test',
    wsUrl: 'ws://test',
    backendUrl: 'http://test',
  }),
}))

import { fetchCameras, snapshotUrl } from '../camera'

describe('max-flow camera helpers', () => {
  afterEach(() => vi.restoreAllMocks())

  it('builds a cache-busted snapshot URL with the camera name', () => {
    const url = snapshotUrl('cam1', 42)
    expect(url).toBe('http://test/api/camera/snapshot?name=cam1&t=42')
  })

  it('omits the name when none is given', () => {
    expect(snapshotUrl(undefined, 7)).toBe('http://test/api/camera/snapshot?t=7')
  })

  it('returns the camera list on success', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: () =>
          Promise.resolve({ available: true, cameras: [{ name: 'cam1', service: 'mjpg' }] }),
      }),
    )
    expect(await fetchCameras()).toEqual([{ name: 'cam1', service: 'mjpg' }])
  })

  it('degrades to an empty list when unavailable', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false }))
    expect(await fetchCameras()).toEqual([])
  })

  it('degrades to an empty list when the request throws', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network')))
    expect(await fetchCameras()).toEqual([])
  })
})
