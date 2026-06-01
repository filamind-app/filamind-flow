/** Mirrors the backend `ShaperAnalysis` schema (POST /api/shaper/analyze). */

/** One shaper family's fitted result on the resonance data. */
export interface ShaperResult {
  name: string
  freq: number
  /** Estimated remaining vibrations, as a percentage (lower is better). */
  vibrations_pct: number
  smoothing: number
  /** Suggested max_accel (mm/s²) to avoid excessive smoothing. */
  max_accel: number
  recommended: boolean
}

/** A shaper's vibration-reduction curve, sampled over the frequency bins. */
export interface ShaperCurve {
  name: string
  vals: number[]
}

export interface ShaperAnalysis {
  recommended_shaper: string | null
  recommended_freq: number | null
  /** The axis this CSV belongs to (x / y), if supplied. */
  axis: string | null
  max_freq: number
  shapers: ShaperResult[]
  /** Frequency bins (Hz) shared by every PSD + shaper-curve series below. */
  freqs: number[]
  psd_x: number[]
  psd_y: number[]
  psd_z: number[]
  psd_sum: number[]
  shaper_curves: ShaperCurve[]
  /** Human-readable calibration log lines (one per fitted shaper). */
  log: string[]
}
