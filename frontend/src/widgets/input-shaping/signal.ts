/** Tiny signal helpers shared by the quality grade, the diagnostics and the
 *  chart annotations. Pure + testable.
 */

/** Median of a list (0 for an empty list). */
export function median(xs: number[]): number {
  if (!xs.length) return 0
  const s = [...xs].sort((a, b) => a - b)
  const m = s.length >> 1
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2
}

/** Ratio of the tallest PSD bin to the median bin — how far the resonance peak
 *  rises above the noise floor. A large value means a clean, trustworthy
 *  capture; ~1 means noise. `null` when there is no spectrum. Capped at 999. */
export function peakSnr(psdSum: number[]): number | null {
  if (!psdSum.length) return null
  const peak = Math.max(...psdSum)
  if (peak <= 0) return null
  const med = median(psdSum)
  if (med <= 1e-12) return 999
  return Math.min(999, peak / med)
}

/** Index of the tallest bin (the dominant resonance), or -1 for empty input. */
export function peakIndex(psdSum: number[]): number {
  if (!psdSum.length) return -1
  let best = 0
  for (let i = 1; i < psdSum.length; i++) if (psdSum[i] > psdSum[best]) best = i
  return best
}
