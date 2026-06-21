import { describe, it, expect } from 'vitest'

import { describeError, httpError } from '../describeError'

describe('describeError', () => {
  it('maps network/fetch failures to the translated backend-unreachable copy (not the raw text)', () => {
    const msg = describeError(new TypeError('Failed to fetch'))
    expect(msg).not.toMatch(/failed to fetch/i)
    expect(msg.length).toBeGreaterThan(0)
    // also matches the other browser variants
    expect(describeError(new Error('NetworkError when attempting to fetch resource'))).toBe(msg)
    expect(describeError(new Error('Load failed'))).toBe(msg)
  })

  it('passes a non-network error through unchanged', () => {
    expect(describeError(new Error('boom'))).toBe('boom')
    expect(describeError('plain string')).toBe('plain string')
  })

  it('httpError surfaces the status code', () => {
    expect(httpError(503)).toMatch(/503/)
  })
})
