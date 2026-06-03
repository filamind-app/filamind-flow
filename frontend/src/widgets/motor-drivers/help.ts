/** Plain-language help copy for the Motor Drivers widget — one source of truth so the
 *  same wording is reused everywhere. Rendered by `HelpNote.vue` behind a collapsed
 *  "ℹ what's this?" toggle, with the matching `HelpIllo` illustration.
 */

export type HelpIlloKey = 'driver' | 'current' | 'chopper' | 'microsteps' | 'stallguard'

export type HelpTopic =
  | 'glossary'
  | 'overview'
  | 'current'
  | 'chopper'
  | 'microsteps'
  | 'stallguard'
  | 'health'
  | 'temperature'
  | 'catalog'
  | 'motor'
  | 'recommend'
  | 'sensorless'
  | 'monitor'

export interface HelpEntry {
  title: string
  body: string
  illo?: HelpIlloKey
}

export interface GlossaryTerm {
  term: string
  def: string
}

/** The jargon that unlocks the dashboard, shown under the `glossary` topic. */
export const GLOSSARY: GlossaryTerm[] = [
  {
    term: 'TMC driver',
    def: 'The chip that turns Klipper’s step/dir signals into the coil currents that spin a stepper motor — e.g. TMC2209, TMC2240, TMC5160. Each motor has one.',
  },
  {
    term: 'Run current',
    def: 'How hard the motor is driven while moving (amps). Too low → skipped steps; too high → overheating. The live value can differ slightly from the configured one because the chip quantises it.',
  },
  {
    term: 'Hold current',
    def: 'The reduced current applied while the motor is idle, to save heat and noise.',
  },
  {
    term: 'Microsteps',
    def: 'How finely each full motor step is subdivided (16/32/…/256). Higher = smoother and quieter motion, with no real loss of torque thanks to interpolation.',
  },
  {
    term: 'StealthChop',
    def: 'A near-silent driving mode, great for Z and idle. Smooth but slightly less precise at high speed.',
  },
  {
    term: 'SpreadCycle',
    def: 'A precise, high-torque driving mode, better for fast X/Y moves. Audible but accurate.',
  },
  {
    term: 'StallGuard',
    def: 'The driver’s load sensor. It enables sensorless homing (detecting a stall instead of using an endstop switch). Its threshold register varies by model (sgthrs / sgt / sg4_thrs).',
  },
  {
    term: 'Sense resistor',
    def: 'A tiny resistor that sets the driver’s current scale. It must match your board; the dashboard shows the configured value.',
  },
  {
    term: 'Interface (UART / SPI)',
    def: 'How the MCU talks to the driver. UART is a single wire (TMC220x family); SPI is a faster multi-wire bus used by the performance parts (2130 / 5160). The TMC2240 can do either.',
  },
]

export const HELP: Record<HelpTopic, HelpEntry> = {
  glossary: {
    title: 'Driver terms',
    body: 'A quick glossary for this dashboard:',
    illo: 'driver',
  },
  overview: {
    title: 'What this shows',
    body: 'Every TMC stepper driver your printer has, read straight from its live Klipper config — one card per motor (X, Y, each Z, the extruder…). This view is read-only: it reports what is configured and what the driver is doing right now. Tuning comes in a later step.',
    illo: 'driver',
  },
  current: {
    title: 'Run / hold current',
    body: 'Run current is how hard the motor is pushed while moving; hold current is the lower idle level. The live figure is what the chip actually applies — it can sit a hair off the configured value because currents come in discrete steps. A driver running hot usually means the run current is set too high for the motor.',
    illo: 'current',
  },
  chopper: {
    title: 'StealthChop vs SpreadCycle',
    body: 'The chopper mode is how the driver shapes the coil current. SpreadCycle is precise and high-torque (good for fast X/Y) but audible; StealthChop is near-silent (good for Z and idle) but slightly softer at speed. “StealthChop < N mm/s” means it stays quiet below that speed, then switches to SpreadCycle above it.',
    illo: 'chopper',
  },
  microsteps: {
    title: 'Microstepping',
    body: 'Each full motor step is electronically subdivided into microsteps (16, 32, … 256). More microsteps = smoother, quieter motion. With interpolation on, the driver smooths up to 256 internally regardless of the configured value.',
    illo: 'microsteps',
  },
  stallguard: {
    title: 'StallGuard (sensorless homing)',
    body: 'StallGuard measures motor load so the axis can home by detecting a gentle stall instead of using a physical endstop. The threshold register differs by model (sgthrs on 2209, sgt on 2130/5160, sg4_thrs on 2240). Tuning it is a later step; here we just show the configured value.',
    illo: 'stallguard',
  },
  health: {
    title: 'Live status',
    body: 'When a motor is enabled (after homing or a jog), the driver reports live flags: overtemperature, short-circuit, and open-load. A green “ok” means no faults; “warning” is an over-temperature pre-warning or open load; “fault” is a short or hard over-temperature. While the motor is disabled the driver reports nothing, so the card shows “idle”.',
    illo: 'driver',
  },
  temperature: {
    title: 'Temperature',
    body: 'Only some drivers (e.g. the TMC2240) have a built-in temperature sensor. On models without one — like the common TMC2209 — temperature reads “no sensor”, which is normal, not an error.',
    illo: 'current',
  },
  catalog: {
    title: 'Where the model facts come from',
    body: 'The interface (UART / SPI), the current cap, and the supported features shown on each card come from a built-in capability map of the TMC family — verified against the Klipper / Kalico driver code. It tells you, for example, that a TMC2208 can’t do sensorless homing while a TMC2209 can, or that only the TMC2240 reports its own temperature. Electrical figures are datasheet-typical; your board, sense resistor, and cooling set the real limits.',
    illo: 'driver',
  },
  motor: {
    title: 'Assigning a motor',
    body: 'Pick the stepper motor wired to each axis from a built-in catalog of 200+ motors. Klipper doesn’t know which motor you fitted — telling FilaMind unlocks its datasheet specs (holding torque, rated current, resistance, inductance), which a later step uses to recommend a safe run current and driver tuning. It’s saved on the printer and changes nothing on the driver by itself.',
    illo: 'current',
  },
  monitor: {
    title: 'Live monitor',
    body: 'Watch a driver in real time while it runs: temperature, StallGuard load (SG_RESULT — it falls toward zero as mechanical load rises), current scale (CS_ACTUAL), and any fault flags (overtemperature, short, open-load). The driver only reports these while the motor is enabled, so move or home the axis to see live data. Read-only — it just observes.',
    illo: 'driver',
  },
  sensorless: {
    title: 'Sensorless homing',
    body: 'Some axes home without an endstop switch: the driver detects the gentle “stall” when the toolhead reaches the end of travel. The StallGuard threshold sets how sensitive that is — too low and it triggers early (stops short), too high and it never triggers (the axis grinds into the frame). This helper lets you set the threshold and test-home one axis, both behind a confirm. Adjust by feel: lower if it stops early, raise if it doesn’t stop — and keep a hand near the power the first few times. If your axis uses a physical endstop, you don’t need this.',
    illo: 'stallguard',
  },
  recommend: {
    title: 'Recommended tuning',
    body: 'Once a motor is assigned, FilaMind can compute a suggested run current and the StealthChop / SpreadCycle register values (pwm_grad, pwm_ofs, hstrt, hend) from the motor’s datasheet specs and your supply voltage — the same physics the klipper_tmc_autotune project uses, so it works even without that add-on installed. The run current defaults to a conservative 70% of the motor’s rating. The result is diffed against your live config; you can then copy it to printer.cfg, or write it live behind a confirm (reversible with Revert, and refused while printing). If the autotune add-on is installed, you can run it instead.',
    illo: 'driver',
  },
}

/** The practical “how to read this” steps, shown once at the top of the dashboard. */
export const STEPS: string[] = [
  'Each card is one stepper driver — its heading is the axis (X / Y / Z / Extruder) and the badge is the chip model.',
  'Run current shows how hard the motor is driven; the live value may differ slightly from the configured “set” value — that’s normal.',
  'Mode tells you SpreadCycle (precise, louder) or StealthChop (quiet); microsteps shows how smooth the motion is.',
  'Home an axis or jog the motor to wake it — live temperature and fault flags only appear while a motor is enabled (idle drivers show “idle”).',
  'Open “advanced registers” on a card to inspect the raw tuning values the driver is using.',
]
