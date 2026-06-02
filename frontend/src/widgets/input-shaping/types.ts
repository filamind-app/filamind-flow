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

/** One machine axis → accelerometer axis mapping from axes-map detection. */
export interface AxisMapping {
  machine_axis: string
  accel_axis: string
  /** "+" or "-". */
  sign: string
  angle_error: number
  confidence: number
  /** True if reconstructed (2-axis / bed-slinger machine). */
  extrapolated: boolean
}

/** Downsampled integrated-velocity series for one machine-axis stroke. */
export interface VelocitySeries {
  axis: string
  t: number[]
  vx: number[]
  vy: number[]
  vz: number[]
  detected_axis: string
  confidence: number
  extrapolated: boolean
}

/** Result of axes-map calibration — the accelerometer's detected orientation. */
export interface AxesMapResult {
  axes_map: string
  /** Accelerometer config section the axes_map goes in (e.g. "adxl345"). */
  chip: string
  status: 'ok' | 'warning' | 'error'
  messages: string[]
  mappings: AxisMapping[]
  euler: Record<string, number>
  /** Gravity magnitude (m/s²). */
  gravity: number
  /** Dynamic noise (mm/s²). */
  noise: number
  noise_grade: 'ok' | 'warning' | 'error'
  current_axes_map: string | null
  matches_current: boolean | null
  accel: number
  extrapolated_axis: number | null
  velocity_series: VelocitySeries[]
  source_files: string[]
}

/** Result of a sustain-frequency hold — a time-frequency spectrogram + timeline. */
export interface StaticExcitationResult {
  axis: string
  freq: number
  duration: number
  max_freq: number
  /** Frequency-bin centres (Hz) — heatmap rows. */
  freqs: number[]
  /** Segment centre times (s) — heatmap columns + energy timeline. */
  times: number[]
  /** Log-normalised power grid [freq][time], 0..1. */
  spectrogram: number[][]
  /** Normalised vibration energy per time, 0..1. */
  energy: number[]
  excited_band_pct: number
  energy_drop_pct: number
  dominant_freq: number
  dominant_ok: boolean
  verdict: string
  source_file: string | null
}
