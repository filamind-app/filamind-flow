import { describe, expect, it } from 'vitest'

import { median, peakIndex, peakSnr } from '../signal'

describe('signal', () => {
  it('takes the median of odd and even lists', () => {
    expect(median([3, 1, 2])).toBe(2)
    expect(median([1, 2, 3, 4])).toBe(2.5)
    expect(median([])).toBe(0)
  })

  it('computes peak-to-median SNR, null for empty or flat-zero input', () => {
    expect(peakSnr([1, 1, 10, 1, 1])).toBe(10)
    expect(peakSnr([])).toBeNull()
    expect(peakSnr([0, 0, 0])).toBeNull()
  })

  it('finds the index of the tallest bin', () => {
    expect(peakIndex([1, 5, 2])).toBe(1)
    expect(peakIndex([])).toBe(-1)
  })
})
