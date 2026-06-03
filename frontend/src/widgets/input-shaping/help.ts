/** Plain-language help copy for the Input Shaping widget — one source of truth so the
 *  same wording is reused everywhere (and the numbers stay anchored to `grade.ts`'s
 *  thresholds). Rendered by `HelpNote.vue` behind a collapsed "ℹ what's this?" toggle.
 */

export type HelpIlloKey = 'flow' | 'peak' | 'shaper' | 'noise' | 'belt' | 'sensor' | 'sweep'

export type HelpTopic =
  | 'glossary'
  | 'analyze'
  | 'grade'
  | 'diagnostics'
  | 'chart'
  | 'shapers'
  | 'config'
  | 'noise'
  | 'belts'
  | 'axesMap'
  | 'sustain'
  | 'vibrations'
  | 'guided'
  | 'history'

export interface HelpEntry {
  title: string
  body: string
  illo?: HelpIlloKey
}

export interface GlossaryTerm {
  term: string
  def: string
}

/** Six terms that unlock most of the jargon, shown under the `glossary` topic. */
export const GLOSSARY: GlossaryTerm[] = [
  {
    term: 'Input shaper',
    def: 'A filter Klipper applies to motion that cancels the printer’s main vibration, so you can print faster without ringing / ghosting.',
  },
  {
    term: 'Resonance',
    def: 'The frequency (Hz) at which an axis naturally vibrates when pushed. Lower = softer / heavier axis; ~40–90 Hz is a healthy printer.',
  },
  {
    term: 'PSD',
    def: 'Power spectral density — how much vibration energy sits at each frequency. The tall peak is the resonance the shaper targets.',
  },
  {
    term: 'Smoothing',
    def: 'A side-effect of shaping that slightly rounds sharp corners. Lower is better; ≤0.1 is minimal, >0.2 starts to soften detail.',
  },
  {
    term: 'Vibration %',
    def: 'How much resonance is left after the shaper. Lower is better; ≤2% is excellent, ≤5% is fine.',
  },
  {
    term: 'max_accel',
    def: 'The acceleration the shaper can sustain without too much smoothing — a suggested SET_VELOCITY_LIMIT / printer.cfg value.',
  },
]

export const HELP: Record<HelpTopic, HelpEntry> = {
  glossary: { title: 'Input shaping terms', body: '' },
  analyze: {
    title: 'Analyzing a resonance CSV',
    body: 'Capture data on the printer with TEST_RESONANCES (or use 🔴 Live tools), then load the .csv here. FilaMind runs Klipper’s own shaper math and recommends a shaper + frequency. Do the X file and the Y file in turn — they combine into one config block.',
    illo: 'flow',
  },
  grade: {
    title: 'What the A–F grade means',
    body: 'A measurement-quality score from five equal parts: peak clarity, leftover vibration, smoothing, frequency (40–90 Hz is healthy), and how clean the resonance is. A/B → apply it; C → usable, skim the tips; D/F → fix the mechanics and re-test.',
  },
  diagnostics: {
    title: 'Reading the diagnostics',
    body: 'Each card maps the measurement to a likely mechanical cause and a fix. Lime = healthy, yellow = worth improving, red = fix before trusting the result. Apply a fix, re-run, and watch the card turn green.',
  },
  chart: {
    title: 'Reading the frequency chart',
    body: 'Solid curves are the measured vibration energy (X+Y+Z total plus each axis). The ▲ marks the dominant resonance. The faint curves are each shaper’s leftover vibration across frequency — the recommended one (pink) dips deepest at your peak.',
    illo: 'peak',
  },
  shapers: {
    title: 'Choosing a shaper',
    body: 'Each row trades leftover vibration against smoothing. ZV / MZV are lightest (clean single resonance); EI is more robust; 2-/3-hump handle broad or multiple resonances but smooth more. FilaMind highlights the best balance.',
    illo: 'shaper',
  },
  config: {
    title: 'Applying the config',
    body: 'This [input_shaper] block carries your X and/or Y result. Copy it into printer.cfg and restart Klipper. The badges show which axes are captured — capture both X and Y for a complete block.',
  },
  noise: {
    title: 'Noise check',
    body: 'Reads the accelerometer’s idle vibration without moving — a quick mount check before testing. Klipper’s rule of thumb: ~1–100 is normal, ~1000+ means a loose sensor or wiring. Fix a noisy mount first or every test is unreliable.',
    illo: 'noise',
  },
  belts: {
    title: 'Belt comparison (CoreXY)',
    body: 'Excites each belt diagonal and overlays the two responses. Matched peak frequencies = even tension. A gap means the lower-frequency belt is looser — tighten it and re-run until the peaks line up.',
    illo: 'belt',
  },
  axesMap: {
    title: 'Axes-map detection',
    body: 'Jogs the toolhead a little in X, then Y, then Z to learn how the accelerometer is mounted, and gives you the axes_map line for printer.cfg. Run it once after fitting or moving the sensor so every later test reads the right axes.',
    illo: 'sensor',
  },
  sustain: {
    title: 'Sustain frequency',
    body: 'Holds the toolhead buzzing at one frequency so you can touch belts, the carriage and the frame by hand to find what rattles. The spectrogram + timeline show whether your target frequency is dominating and when a touch quieted it.',
  },
  vibrations: {
    title: 'Vibrations profile',
    body: 'Sweeps many speeds along each motor angle to map where the machine runs smoothest and which speeds hit a resonance. Favour the smoothest speeds for print / travel moves and avoid the flagged ones. Symmetry % shows how well the two motors match.',
    illo: 'sweep',
  },
  guided: {
    title: 'Guided vs. manual',
    body: 'Guided walks the whole flow — Noise → Belts → Shaper X → Shaper Y → Vibrations → Pressure — with a pass / fail gate at each step. Use it for a full tune. Switch to 📈 Analyze or 🔴 Live tools when you just want one specific tool.',
    illo: 'flow',
  },
  history: {
    title: 'History & trends',
    body: 'Each calibration is saved (in this browser) with its grade and score. The ▲/▼ arrow compares a run to the previous test of the same axis — up means a cleaner capture or a stiffer axis, down means more noise or a softer axis.',
  },
}
