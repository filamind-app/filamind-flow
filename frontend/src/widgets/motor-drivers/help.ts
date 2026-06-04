/** Plain-language help copy for the Motor Drivers widget — one source of truth so the
 *  same wording is reused everywhere. Rendered by `HelpNote.vue` behind a collapsed
 *  "ℹ what's this?" toggle, with the matching `HelpIllo` illustration.
 */

export type HelpIlloKey =
  | 'driver'
  | 'current'
  | 'chopper'
  | 'microsteps'
  | 'stallguard'
  | 'homing'
  | 'coolstep'

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
  | 'homing'
  | 'sensorless'
  | 'monitor'
  | 'motorsync'
  | 'registers'
  | 'coolstep'

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
  motorsync: {
    title: 'Motor synchronization',
    body: 'When one axis is driven by two or more motors (dual or quad-Z, dual-X), their microstep phases can drift apart and fight each other — adding noise and losing torque. The motors_sync add-on measures each motor with an accelerometer and nudges them back into phase. It’s a separate add-on; if it’s installed FilaMind can run or calibrate it here (it moves the toolhead, so it’s gated). If not installed, this just explains what it does.',
    illo: 'driver',
  },
  monitor: {
    title: 'Live monitor',
    body: 'Watch a driver in real time while it runs: temperature, StallGuard load (SG_RESULT — it falls toward zero as mechanical load rises), current scale (CS_ACTUAL), and any fault flags (overtemperature, short, open-load). The driver only reports these while the motor is enabled, so move or home the axis to see live data. Read-only — it just observes.',
    illo: 'driver',
  },
  homing: {
    title: 'How this axis homes',
    body: 'Klipper finds each axis’s zero one of a few ways, and FilaMind reads which from your config rather than guessing: a physical endstop switch (the classic microswitch — most printers), sensorless homing (the TMC driver senses the motor stalling at the end of travel — no switch), or the Z probe (the same sensor used for bed mesh finds Z=0). This panel adapts to whichever your axis uses — live switch state and a plain test-home for a physical endstop, a StallGuard tuner for sensorless, or a pointer to the probe tools for a probed Z. Extra motors sharing a rail (a second Z, the extruder) don’t home on their own, so they show nothing here.',
    illo: 'homing',
  },
  sensorless: {
    title: 'Sensorless homing',
    body: 'Some axes home without an endstop switch: the driver detects the gentle “stall” when the toolhead reaches the end of travel. The StallGuard threshold sets how sensitive that is — too low and it triggers early (stops short), too high and it never triggers (the axis grinds into the frame). This helper lets you set the threshold and test-home one axis, both behind a confirm. Adjust by feel: lower if it stops early, raise if it doesn’t stop — and keep a hand near the power the first few times. If your axis uses a physical endstop, you don’t need this.',
    illo: 'stallguard',
  },
  coolstep: {
    title: 'CoolStep (load-adaptive current)',
    body: 'CoolStep lets the driver lower the coil current when the motor isn’t working hard, then raise it back under load — saving heat and noise. It’s a coupled feedback loop with five interacting registers (semin/semax/seup/sedn/seimin), so instead of five raw knobs this is a single on/off that applies the same vetted set the klipper_tmc_autotune project uses (semin 2, semax 4, seup 3, sedn 2, seimin 1). It only acts above a velocity threshold, and being too aggressive under high acceleration can drop steps — leave it off unless you know you want it. Live only: a restart or “reset to config” restores your saved values.',
    illo: 'coolstep',
  },
  registers: {
    title: 'Editing registers (advanced)',
    body: 'The advanced editor writes individual TMC tuning registers to the driver live — chopper timing (toff/tbl/hstrt/hend), StealthChop PWM (pwm_grad/pwm_ofs/…), CoolStep, StallGuard sensitivity, and the StealthChop↔SpreadCycle speed threshold (in mm/s). Which fields appear, and their valid range, come from the printer-side safety policy — not the browser — because the driver silently truncates an out-of-range value instead of erroring, so the server clamps and rejects. Raw current-scaling and short/overtemp-protection registers are deliberately not editable here (current goes through the recommender/run-current path; microsteps need a config change + restart). Every edit is live only: INIT_TMC (the “reset to config” button), a firmware restart, or a power-cycle restores your saved values. Riskier knobs need a per-field confirm, and all writes are refused while the printer is printing or paused.',
    illo: 'chopper',
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
