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
  /** Filename this came from, when imported/captured on the printer host. */
  source_file: string | null
}

/** A resonance CSV Klipper wrote on the printer host. */
export interface ResonanceFile {
  name: string
  path: string
  size: number
  /** Last-modified time (epoch seconds). */
  mtime: number
  /** Axis guessed from the filename (x / y), if any. */
  axis: string | null
}

export interface ResonanceFilesResponse {
  files: ResonanceFile[]
  dirs: string[]
}

/** One accelerometer chip's idle noise (mean PSD per axis). */
export interface NoiseChip {
  label: string
  x: number
  y: number
  z: number
}

/** Result of MEASURE_AXES_NOISE — the accelerometer's idle noise floor. */
export interface NoiseResult {
  chips: NoiseChip[]
  max_noise: number
  /** good (<100) · elevated (100–1000) · high (≥1000), per Klipper's guidance. */
  grade: 'good' | 'elevated' | 'high'
  ok: boolean
  threshold: number
}

/** Two belt-direction captures for a CoreXY belt-tension comparison. */
export interface BeltComparison {
  /** Excited along the (1,1) diagonal. */
  belt_a: ShaperAnalysis
  /** Excited along the (1,-1) diagonal. */
  belt_b: ShaperAnalysis
}
