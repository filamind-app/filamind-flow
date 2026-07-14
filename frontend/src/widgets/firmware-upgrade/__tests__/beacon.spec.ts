import { describe, expect, it } from 'vitest'

import { beaconUpToDate, beaconVerCore } from '../beacon'

describe('beaconVerCore', () => {
  it('extracts the X.Y.Z core from either version form', () => {
    expect(beaconVerCore('2.1.0')).toBe('2.1.0') // probe report
    expect(beaconVerCore('v2.1.0')).toBe('2.1.0') // plugin tag with a v prefix
    expect(beaconVerCore('v2.1.0-3-gabc')).toBe('2.1.0') // git-describe detail dropped
    expect(beaconVerCore('2.1')).toBe('2.1.0') // two-part normalised to three
  })

  it('returns empty for a missing or non-numeric version', () => {
    expect(beaconVerCore(null)).toBe('')
    expect(beaconVerCore(undefined)).toBe('')
    expect(beaconVerCore('latest')).toBe('')
  })
})

describe('beaconUpToDate', () => {
  it('is up to date when the running version matches the newest available', () => {
    expect(beaconUpToDate('2.1.0', '2.1.0')).toBe(true)
    expect(beaconUpToDate('2.1.0', 'v2.1.0')).toBe(true) // prefix-only difference
  })

  it('is up to date when the probe is AHEAD of the newest tag (the #610 case)', () => {
    // The reporter's probe ran v2.1.0 while the plugin's newest tag was v2.0.0 (the flasher ships
    // HEAD, which is ahead of the last tag) - that must read as up to date, not "needs flash".
    expect(beaconUpToDate('2.1.0', 'v2.0.0')).toBe(true)
    expect(beaconUpToDate('2.10.0', '2.9.0')).toBe(true) // numeric compare, not lexical
  })

  it('is NOT up to date when the probe is behind', () => {
    expect(beaconUpToDate('2.0.0', 'v2.1.0')).toBe(false)
    expect(beaconUpToDate('2.9.0', '2.10.0')).toBe(false)
  })

  it('falls back to "offer Flash" when either version is unknown', () => {
    expect(beaconUpToDate(null, '2.1.0')).toBe(false) // probe version unreadable
    expect(beaconUpToDate('2.1.0', null)).toBe(false) // plugin has no tags
    expect(beaconUpToDate(null, null)).toBe(false)
  })
})
