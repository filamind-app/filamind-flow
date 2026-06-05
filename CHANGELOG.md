# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.72.0] - 2026-06-05

### Added

- **Firmware Manager — Guided new-board wizard (#118).** A new **🧭 Guided** tab walks a new
  control board through four steps — detect the board, configure & build a profile, add & assign
  the device, then build & flash and verify it's in sync with the host. Each step reflects the
  **live** firmware state (it turns green when satisfied) and deep-links into the tab where you do
  it; it doesn't duplicate the build/flash logic or bypass any confirm. The widget now lands on
  Guided on first run when no board is set up yet, mirroring the other widgets' first-run flow.

### Changed

- **Input Shaping — the result is reunited with the action (#116).** The recommended shaper,
  A–F measurement grade, frequency-response chart and shaper table now render in **every working
  view** — including **Guided**, which previously showed only per-step pass/fail badges and hid
  the rich result the wizard had just computed. A pinned **“printer.cfg ready”** bar (captured
  axes + 📋 Copy + 💾 Archive) now sits at the top of every working view, so after a capture the
  widget's payoff is one tap away instead of buried below the on-printer panels. *(The optional
  Live-panel section grouping is a minor follow-up.)*

### Changed

- **Sidebar entries stay on one line, and the Firmware widget is renamed to “Firmware Manager” (#135).**
  After per-widget icons were added (#121), the Firmware entry's long label wrapped next to the
  icon, making the button look oversized. Sidebar nav items now use a fixed-width icon slot + a
  truncating single-line label, so every entry is the same compact height. The widget's display
  title is now **Firmware Manager** (it builds, flashes, and manages firmware across MCUs — not
  only "upgrades"); its id/route (`firmware-upgrade`) is unchanged.

### Added

- **App shell — deep-linking, mobile navigation, and wayfinding (#121).**
  - The current view is now synced to `location.hash` (e.g. `#motor-drivers`), so a widget page
    can be **bookmarked and survives a reload** — back/forward work too. (The empty Dashboard
    clears the hash cleanly.)
  - On narrow screens the sidebar is now an **off-canvas drawer** with a ☰ toggle in the header
    and a tap-to-dismiss backdrop — previously there was *no* navigation at all below the `md`
    breakpoint (a portrait tablet had no way to switch widgets).
  - Each widget carries its own **sidebar icon** (`WidgetDefinition.icon`: 🔧 / 📈 / ⚙) instead of
    the same generic glyph for all.

### Removed

- Dead `spanClass` grid logic in `WidgetFrame` (the shell always renders a single column, so it
  never applied).

### Added

- **Accessibility pass — completed (#114).** Accessible names on the shared primitives: the
  `WidgetTabs` tablist (`aria-label="Views"`) and the `ComboSelect` search input + options
  listbox. This closes out the a11y review item: the resonance/vibration **charts already carry
  `role="img"` + `aria-label`**, the motor sparkline is `aria-hidden` (its value is shown as
  text), **keyboard focus rings** shipped in v0.65.1 (#115), and the dense Configure/External
  firmware screens gained touch-accessible help in v0.69.0 (#117). Status badges convey state
  with text + symbols, not color alone.

## [0.69.0] - 2026-06-05

### Changed

- **Firmware Upgrade — information-architecture reorg (#117).** The widget now uses the house
  **`WidgetTabs`** strip — **🩺 Status / 🔧 Configure / 🖥 Devices / 📦 External** — instead of a
  full-screen mode swap + footer buttons, so every area is one tap away (and navigation matches
  the other widgets). **External firmware** is promoted from a buried last-child of the Devices
  manager to its own top-level tab. The Configure and External screens gained touch-accessible
  **`HelpNote`** explanations (previously only hover `title=` tooltips existed there).

## [0.68.2] - 2026-06-05

### Fixed

- **The motor dropdown showed only the first 50 motors (#130).** `ComboSelect` capped the rendered
  list at 50, so with no search text you couldn't reach the rest — bad when you don't remember a
  model name and want to browse. It now renders the full filtered list (the dropdown scrolls), is
  taller for easier browsing, scrolls the highlighted option into view during ↑/↓ keyboard
  navigation, and gives each combobox instance unique option ids (fixes a latent duplicate-id
  across the per-stepper pickers).

### Changed

- **Quick-win copy/naming fixes (#122).** Resolved several small inconsistencies from the UX
  review: Input Shaping's fourth view is now consistently **🕘 History** (tab label aligned with
  the intro + help topic); the Analyze tab's compare button is **⇄ compare CSVs** to distinguish
  it from the Live "compare belts" tool; the Firmware Configure screen's `help` checkbox is now
  **option docs** (distinct from the standard ℹ help layer) and its build button is **build
  profile** (vs the per-device build on Status — and the Devices caption no longer contradicts
  it); the Firmware empty state is now an actionable **"+ Add your first board →"** button.

## [0.68.0] - 2026-06-05

### Changed

- **Motor Drivers — lower card density + earlier wizard access (#119).** Each driver card now
  keeps only the live-tuning essentials inline (chopper mode, microsteps, temperature, StallGuard);
  the secondary specs (sense resistor, interpolation, interface, current cap, capability chips)
  collapse behind a per-card **▸ details** toggle. The Dashboard / 🧭 Guided tab strip now shows
  as soon as the printer is reachable (not only after drivers load), so the wizard is discoverable
  from the start. The advanced register editor's toggle uses a distinct **🛠** glyph so it no longer
  collides with the recommend panel's ⚙.

## [0.67.0] - 2026-06-05

### Changed

- **Navigation converged on one shared tab strip (#112).** A new generic `components/ui/
  WidgetTabs.vue` (the persistent top tab strip, active = `bg-brand-cyan ring-2 ring-ink`,
  type-safe over the tab-id union, ARIA `tablist`/`tab`) replaces the bespoke per-widget strips.
  Input Shaping and Motor Drivers now use it, so navigation looks and behaves identically across
  widgets. (Firmware Upgrade adopts it as part of its IA reorg, #117.)

### Added

- **Shared `ComboSelect` dropdown/combobox primitive (#120).** A reusable typeahead select
  (`components/ui/ComboSelect.vue`): one control that opens a filtered dropdown with keyboard
  navigation (↑/↓/Enter/Esc), ARIA `combobox`/`listbox`/`option` roles, optional clear, and a
  capped result list — the convention for every long option list going forward.

### Changed

- **The Motor Drivers motor picker is now a dropdown** instead of an always-open inline list of
  200+ rows. It uses the new `ComboSelect` (search by model or maker; specs shown per option),
  so a card stays compact until you actually pick. Future long pickers (filaments, boards,
  profiles) should reuse the same primitive.

### Added

- **Keyboard focus is now visible across the app (part of #115, accessibility).** Every
  interactive element (links, buttons, summaries, inputs, selects) gets a clear `brand-cyan`
  focus-visible outline. It uses `outline` (not `box-shadow`, so it never fights the brutal
  shadow) and only shows for keyboard navigation, leaving the dense pointer UI unchanged.

### Fixed

- **Touch targets on tablets (part of #115).** Many compact buttons (notably the firmware
  flash/build actions shrunk to `text-[10px]`) were well under the ~44px tap minimum. Branded
  buttons (`.nb-btn`) now get a 44px min-height on coarse-pointer (touch) devices only, so the
  printer-side tablet is usable while the desktop layout stays compact. (The cosmetic button-size
  normalization follows in the per-widget reorg PRs.)

## [0.65.0] - 2026-06-05

### Fixed

- **Firmware flashing now requires explicit confirmation (#111, P0).** Every flash entry point —
  per-device **flash** / **build & flash**, the **batch** flash actions, and the **Beacon** probe
  flash — previously wrote firmware **immediately on click**, with no preview or confirm, while the
  help text promised FilaMind "confirms before irreversible steps". Flashing is destructive (a
  mid-flash interruption can brick a board), so this was a safety gap. A new `FirmwareFlashConfirm`
  dialog now stands in front of every flash: it previews the flash plan (`command` + warnings +
  ready/blocked, via the existing `fetchFlashPlan`) for a single device, lists the affected devices
  for a batch, and requires an "I understand…" acknowledgement before anything writes. A plan that
  reports `ready: false` (e.g. a print is running) blocks the action. This brings Firmware in line
  with Motor Drivers and Input Shaping, which already gate every write.

### Removed

- The orphaned `FirmwareFlashPanel.vue` (imported nowhere) — its plan→confirm→flash pattern is now
  served by the gated flash path above, removing a second, dead flash UI.

### Added

- **Motor Drivers — register-editor polish (P10c, #102).** Completes the advanced editor:
  - **CoolStep as a single toggle.** CoolStep is a coupled five-register feedback loop, so
    instead of five raw boxes the editor offers one **enable / off** control that applies the
    `klipper_tmc_autotune`-vetted set (`semin 2 / semax 4 / seup 3 / sedn 2 / seimin 1`) or
    disables it (`semin 0`) — via a new gated `POST /api/drivers/coolstep`, with its own
    illustrated help note.
  - **StallGuard polarity hints.** The `sgthrs` / `sg4_thrs` / `sgt` rows now show the per-model
    polarity inline ("higher = more sensitive" vs the signed `sgt`'s "lower = more sensitive"),
    so the sensitivity direction isn't backwards on SPI drivers.
  - A **`toff` pairing note** (if you set `toff` to 1, keep `tbl` ≥ 1).

## [0.63.0] - 2026-06-05

### Added

- **Motor Drivers — advanced register editor (P10b, #102).** Each driver card gains a
  **⚙ tune registers (advanced)** panel that edits the safe subset of its TMC registers live,
  driven entirely by the server's `field_policy` (the browser never decides what's editable or
  the bounds):
  - chopper timing (`toff` / `tbl` / `hstrt` / `hend`), StealthChop PWM (`pwm_grad` / `pwm_ofs`
    / `pwm_freq` / …), CoolStep (`semin` / `semax` / …), StallGuard sensitivity, and the
    StealthChop↔SpreadCycle crossover threshold **in mm/s** (Klipper does the TSTEP conversion
    via `VELOCITY=`, and refuses it on a clock-less driver like the 2660);
  - the right control per field — number (with the server's clamp range), toggle, select, or a
    mm/s field — with **per-field confirm** on riskier knobs, and non-editable `driver_*`
    registers shown read-only beneath;
  - a **"↺ reset to config"** (`INIT_TMC`) undo and a persistent "live only — a restart restores
    it" note; raw current-scaling and protection registers are not editable here.
  - New `POST /api/drivers/field` (gated + server-clamped) and `GET /api/drivers/field-policy/{model}`.

## [0.62.0] - 2026-06-04

### Added

- **Motor Drivers — register-edit safety foundation (P10a, #102).** A new server-side
  `field_policy` module is the single source of truth for which TMC registers may be edited
  live and within what bounds — the load-bearing safety layer for advanced-register editing,
  because `SET_TMC_FIELD VALUE=` *silently mask-truncates* out-of-range values rather than
  erroring. It provides:
  - an **allowlist** (only catalogued fields are editable; everything else is display-only);
  - a **per-field clamp** whose range is derived from the register **bit-mask** (so it provably
    matches the silicon), with **per-model signedness** — `sgt` is a signed −64…63, while
    `sgthrs` / `sg4_thrs` are unsigned 0–255;
  - a **blocklist** of raw current-scaling (`irun`, `globalscaler`, `vsense`, …) and
    protection-defeat (`diss2g`, `test_mode`, `overvoltage_vth`, …) fields, plus `mres` /
    `microsteps` (which would desync Klipper's step distance), that are never written live;
  - a **per-model current cap** `I_cap = min(code_cap[model], motor rating)` — the TMC2240 cap
    is computed from its `rref` — surfaced per driver as `current_cap` on `/api/drivers/status`.

### Changed

- The sensorless StallGuard write (`POST /api/drivers/stallguard`) now **enforces the field
  range server-side** (the client's `max=` was not trusted): a 2209 `sgthrs` of 300, or a signed
  `sgt` of 64, is rejected before any g-code is sent.
- Driver writes and test-homes are now refused while the printer is **printing, paused, or in an
  error state** (previously only while actively printing).
- `/api/drivers/status` records gained `rref` and `current_cap` per driver.

### Fixed

- **The current-cap warning used the driver's sanity-ceiling, not the real limit (#102).** A
  TMC5160's catalog cap (10.6 A) is only a board sanity ceiling, so the dashboard would show
  "≤ 10.6 A" and not warn until ~9.5 A — dangerously permissive. The "near cap" warning and the
  cap label now use the effective `current_cap` (min of the model code cap and the assigned
  motor's rating), so once a motor is assigned the real motor-bound limit drives the warning.

## [0.61.2] - 2026-06-04

### Fixed

- **Physical-endstop switch state could show `—` on printers that key endstops by stepper name
  (#106).** `GET /api/drivers/endstops` returns Moonraker's raw keys, which are `stepper_x` on
  some printers (the SV08) and the bare axis letter `x` on others. The P9 physical-homing panel
  looked up only the axis letter, so the live switch state wouldn't render on the former. A new
  unit-tested `endstopStateFor()` tries the stepper section name first, then the axis letter.

## [0.61.1] - 2026-06-04

### Fixed

- **Homing classifier missed sensorless when the endstop pin had whitespace after the colon
  (#104).** Klipper parses `endstop_pin` as `chip:pin` split on the first colon with whitespace
  stripped from each side, so `tmc2209_stepper_x: virtual_endstop` (a stray space — present
  verbatim in the SV08's own `printer.cfg`) is a valid sensorless virtual endstop. The P9
  classifier used an exact `:virtual_endstop` substring test and wrongly classified that axis
  as a **physical endstop**. It now normalises the pin the way Klipper does (split + strip,
  case-insensitive), so spaced and unspaced forms classify identically. Caught by live-verify
  on the SV08, where `stepper_x` (spaced) was mislabelled while `stepper_y` (unspaced) was not.

## [0.61.0] - 2026-06-04

### Added

- **Motor Drivers — homing coverage (P9, #101).** Each axis's homing method is now classified
  from its `[stepper_*].endstop_pin` using Klipper's own rule, and surfaced on the card as a
  method-aware **🏠 homing** panel instead of assuming "has a StallGuard register ⇒ sensorless":
  - **Physical endstop** → live switch state (open / TRIGGERED), an on-demand **↻ check**, and a
    plain gated **test-home** (the switch stops the move, so a softer warning than sensorless).
  - **Sensorless (StallGuard)** → the StallGuard tuner, now with **per-model polarity**: the
    signed `sgt` register (TMC2130 / 5160 / 2660) uses its true −64…63 range where _lower_ is
    more sensitive, while `sgthrs` / `sg4_thrs` (2209 / 2240) stay unsigned 0–255 where _higher_
    is more sensitive — so the control no longer feels backwards on SPI drivers.
  - **Z probe** → a pointer to the bed-leveling tools (no StallGuard to tune here).
  - **Virtual / shared** → a clear note; extra motors on a shared rail (a second Z, the extruder)
    show no homing UI.

  The sensorless tuner (and the Guided wizard's sensorless step) now appear **only** for axes that
  actually home sensorless — fixing the case where a probe-homed Z or a switch-homed axis on a
  StallGuard-capable driver wrongly offered sensorless tuning. New `GET /api/drivers/endstops`.

## [0.60.0] - 2026-06-03

### Added

- **Firmware Upgrade widget — built-in help layer (#82).** Per the project's widget-UX rule
  (already used by Input Shaping and Motor Drivers), the Firmware Upgrade widget now has a
  collapsed help row: a **glossary**, **"what's this?" explanations** for each section
  (host/MCU sync, toolchain badges, services, devices, flashing) with **inline SVG
  illustrations**, and a **"build → flash" quick guide**. Collapsed by default — zero clutter.

## [0.59.1] - 2026-06-03

### Fixed

- **Motor Drivers: a driver with no `stealthchop_threshold` set now shows "SpreadCycle"
  instead of "—".** An unset threshold means Klipper's default of 0, i.e. SpreadCycle — so
  the card reports the real mode rather than an unknown one (e.g. the SV08 extruder). (#85)

## [0.59.0] - 2026-06-03

### Added

- **Motor Drivers P8 — motor synchronization (roadmap complete).** A printer-level panel
  drives the optional **motors_sync** add-on to align the microstep phase of multiple motors
  on one axis (dual / quad-Z, dual-X). It detects whether the add-on is installed; if so it
  offers **Sync motors** / **Calibrate** behind a confirm + crash warning (accelerometer-based,
  moves the toolhead, refused while printing); if not, it explains what it does. This completes
  the Motor Drivers widget roadmap (**P1–P8**).
  - Backend: **`GET /api/drivers/motors-sync`** (availability) + **`POST /api/drivers/motors-sync`**
    (`SYNC_MOTORS` / `SYNC_MOTORS_CALIBRATE`, gated).

## [0.58.0] - 2026-06-03

### Added

- **Motor Drivers P7 — guided tuning wizard.** A new **🧭 Guided** view walks one driver
  through the whole flow in order — **choose axis → assign motor → recommend & apply →
  (sensorless) → done** — with a step breadcrumb, per-step guidance, and Back/Next (the
  sensorless step is skipped automatically when the model doesn't support it). It **reuses the
  same panels** as the dashboard, so there's one source of truth and the same safety gating.
  A Dashboard / Guided mode strip switches between the full dashboard and the wizard.

### Changed

- Motor Drivers intro updated (it's no longer read-only — it inspects, recommends, and applies).

## [0.57.0] - 2026-06-03

### Added

- **Motor Drivers P6 — live monitor.** A per-driver, read-only "live monitor" panel polls
  the driver's telemetry (~1.5 s) and shows **temperature**, **StallGuard load (SG_RESULT)**
  with an inline sparkline, **current scale (CS_ACTUAL)**, and any **fault flags**
  (overtemperature / short / open-load / standstill). The driver only reports this while the
  motor is enabled, so an idle motor shows a hint to move/home the axis. No writes, no motion.
  - Backend: fast, focused **`GET /api/drivers/live/{stepper}`** (one driver's `get_status`,
    no config re-read).

## [0.56.0] - 2026-06-03

### Added

- **Motor Drivers P5 — sensorless-homing helper.** For drivers that support sensorless
  homing, a new panel lets you tune the **StallGuard threshold** (`sgthrs` / `sgt` /
  `sg4_thrs`) and **test-home one axis** — both behind an explicit confirm and refused
  server-side while printing. The test-home carries a loud crash warning (a wrong threshold
  can drive the axis into the frame). Guidance: lower if it stops early, raise if it doesn't
  stop. Shown only where the model actually supports sensorless homing.
  - Backend: **`POST /api/drivers/stallguard`** (validated field + value) and
    **`POST /api/drivers/home`** (`G28 <axis>`, gated).

## [0.55.1] - 2026-06-03

### Fixed

- **Motor Drivers: Revert now fully restores the run current.** `INIT_TMC` re-applies the
  configured register *fields* but does **not** undo a `SET_TMC_CURRENT`, so after applying
  a recommendation the motor stayed at the applied current on Revert. Revert now also issues
  `SET_TMC_CURRENT` with the stepper's **configured** run/hold current (read from the live
  config), so it returns to exactly the pre-apply state. (#93)

## [0.55.0] - 2026-06-03

### Added

- **Motor Drivers P4 — apply tuning.** The recommendation can now be acted on, three ways:
  **copy a printer.cfg block** (always safe, no write); **apply it live** to the driver via
  `SET_TMC_CURRENT` / `SET_TMC_FIELD` behind an **explicit confirm**; or **run AUTOTUNE_TMC**
  when the `klipper_tmc_autotune` add-on is installed. A **Revert** button (`INIT_TMC`)
  restores the configured values, and the dashboard refreshes to show the new live numbers.
  - **Safety:** every live write is **refused server-side while the printer is printing**,
    requires the UI confirm, validates all values (no g-code injection), and is reversible.
  - Backend: `drivers_apply` service + **`POST /api/drivers/config-block` · `/apply` · `/init`
    · `/autotune`**.

### Changed

- The "Recommended tuning" panel is no longer preview-only — it now offers copy / apply /
  revert / autotune.

## [0.54.0] - 2026-06-03

### Added

- **Motor Drivers P3 — tuning recommender.** Once a motor is assigned to a stepper, each
  card can compute a suggested **run current** plus the StealthChop / SpreadCycle register
  values (**pwm_grad, pwm_ofs, hstrt, hend**) from the motor's datasheet specs and your
  supply voltage — a faithful port of `klipper_tmc_autotune`'s `motor_constants` physics, so
  it works **even without that add-on installed**. The run current defaults to a conservative
  70% of the motor's rating (overridable). Results are shown as a **preview diffed against the
  live config** (changed values highlighted), with the max StealthChop speed; **nothing is
  written to the driver** — applying is a later, safety-gated step (P4).
  - Backend: pure `motor_constants` + `recommender` services; **`POST /api/drivers/recommend`**
    (404 unknown motor, 422 if the motor lacks the needed datasheet specs).

## [0.53.1] - 2026-06-03

### Fixed

- **Motor picker showed stale results while searching.** The baked motor catalog had 5
  duplicate entries (the same LDO models appear in two source `.cfg` files with identical
  specs), so the picker's `v-for` keys weren't unique and Vue mis-tracked the list as you
  typed. The catalog is now **deduplicated by model** (202 unique motors), the picker uses
  a robust key, and a regression test guards against duplicate models. (#89)

## [0.53.0] - 2026-06-03

### Added

- **Motor Drivers P2b — motor picker.** Each driver card now lets you assign the stepper
  **motor** wired to that axis from a built-in catalog of **200+ motors** (searchable by
  model or manufacturer). The assigned motor's datasheet specs — holding torque, rated
  current, resistance, inductance — show on the card, and the choice is **persisted on the
  printer** (`<data_dir>/motor-mapping.json`). This sets up the upcoming current/register
  recommender; it changes nothing on the driver by itself.
  - Backend: motor database baked to `backend/app/data/motor_catalog.json` (via
    `scripts/bake_motor_catalog.py` from the vendored CSV); new endpoints
    **`GET /api/drivers/motors`** (the catalog) and **`GET`/`POST /api/drivers/mapping`**
    (read / assign). `GET /api/drivers/status` now attaches the assigned `motor` per driver.
  - A "what's this?" help note explains why assigning a motor matters.

## [0.52.0] - 2026-06-03

### Added

- **Motor Drivers P2a — driver capability map.** Each driver card is now annotated with
  authoritative reference data for its TMC model, from a curated capability catalog
  (verified against the Klipper / Kalico driver code): **communication interface**
  (UART / SPI / both), the **current cap**, and accurate **capabilities** (StealthChop /
  SpreadCycle / CoolStep / StallGuard / temperature) — so the chips reflect what the model
  truly supports rather than only what the config exposes. A ⚠ hint flags a run current
  near the model's rated cap, and a new "where the model facts come from" help note explains
  the source.
  - New endpoint **`GET /api/drivers/catalog`** returns the full capability map (keyed by
    model, with aliases like 2225→2208 / 2226→2209 / 5161→5160), backing this and the
    upcoming motor picker.
  - Data baked to `backend/app/data/driver_catalog.json`; covers TMC2208 / 2209 / 2130 /
    2240 / 2660 / 5160 (and aliases). Unknown models still render fully from live config.

## [0.51.0] - 2026-06-03

### Added

- **New widget — Motor Drivers (P1: read-only dashboard).** A live inventory of every
  TMC stepper driver on the printer, discovered straight from the Klipper config — one
  card per motor (X / Y / each Z / extruder…). Each card shows the driver model, run &
  hold current (live vs configured), chopper mode (SpreadCycle / StealthChop + threshold),
  microsteps, sense resistor, StallGuard threshold, live temperature (or “no sensor” on
  models without one), a live health badge (idle / ok / warning / fault from `drv_status`),
  capability chips, and a collapsible advanced-register view.
  - **Generic across every Klipper printer** — drivers are detected from config, not
    assumed; all TMC models are handled (2209 / 2208 / 2130 / 2240 / 5160 / 2660…), with
    model-specific fields (temperature sensor, StallGuard register name) resolved from
    what the running config actually exposes.
  - Built-in **help layer** (the project UX rule): a glossary, per-section “what’s this?”
    notes with inline SVG illustrations, and a “how to read this” step list.
  - Backend: `drivers_service` + **`GET /api/drivers/status`**.

### CI

- **Releases now publish automatically.** Pushing a `vX.Y.Z` tag triggers
  `.github/workflows/release.yml`, which creates the GitHub Release from the matching
  `CHANGELOG.md` section. Fixes release publishing that had silently stalled at v0.42.1
  (11 tags with no Release; now backfilled). (#80)

### Docs

- **CONTRIBUTING**: documented three project norms — the widget-UX rule (every widget
  ships explanations + practical steps + inline SVG illustrations), the
  discovered-problem → typed GitHub issue → patch-PR rule, and the release process.

## [0.50.1] - 2026-06-03

### Fixed

- **Firmware Upgrade widget no longer goes blank / shows a bare "Failed to fetch".** When the
  backend was briefly unreachable, the silent 6 s refresh cleared the error and left no fresh
  data, so the widget rendered an **empty panel** (and the initial failure showed only the raw
  `Failed to fetch`). It now keeps the last good data on a transient refresh failure, shows a
  clear **"Cannot reach the FilaMind backend — check that the filamind-flow service is running"**
  message with a **Retry** button, and a fallback line instead of a blank panel.

## [0.50.0] - 2026-06-03

### Added — Input Shaping: every test type feeds the Audit (UX overhaul, 7 of 7 — complete)

- **The Audit now aggregates every result, not just shaper runs.** Each live tool — accelerometer
  noise, belt comparison, axes-map, sustain frequency, and the vibrations profile — records an
  entry when it completes, rendered as a per-property card alongside the shaper calibrations and
  the archived configs/captures. One organized, engineered place to review every test by property.
- New pure record builders in `audit.ts` (one per tool, reusing the existing belt / axes-map /
  result verdicts) with unit coverage; `ResonanceFromPrinter` emits a `recorded` event per tool.
- **This completes the Input Shaping widget reorganization** (v0.45.0 → v0.50.0): four-view IA,
  inline help + illustrations, per-tool motion confirms, a persistent host archive, a unified
  upload/host file source, and the aggregated per-property Audit.

## [0.49.0] - 2026-06-03

### Changed — Input Shaping: History becomes the aggregated Audit (UX overhaul, 6 of N)

- **The History tab is now "Audit"** — one place that aggregates past results, merging this
  browser's records with the on-host **archive** (saved configs + captures). Each result renders
  as a card with its properties in **separate labelled fields** (the shaper factor breakdown,
  grade, and trend ▲/▼ vs the previous same-axis run), newest-first.
- New pure `audit.ts` (unified `AuditRecord` model + per-kind retention + a one-time, idempotent
  fold-in of the legacy grade-history — additive, the old localStorage is never cleared) with a
  unit-test suite. Shaper analyses now also record an audit entry.
- The other live-tool results (noise / belts / axes-map / sustain / vibrations) join the Audit in
  the next release.

## [0.48.0] - 2026-06-03

### Added — Input Shaping: unified CSV source + archive browser (UX overhaul, 5 of N)

- **One place to pick the CSV to analyse.** The Analyze view now has a `CsvSourceChooser` with a
  segmented **📤 Upload** ⟷ **🖥 From printer** control. "From printer" lists both the resonance
  CSVs on the host *and* the persistent archive, so the previously-separate upload and host-import
  paths are unified — all flowing into the one analysis path (and carrying the advanced params
  either way).
- **Archive browser.** Saved runs are listed with per-file **download** and **delete**, a 💾 **save**
  on each host capture, and a 💾 **Archive** button beside the config block's Copy — so a generated
  `[input_shaper]` or a scan CSV can be kept as a deletable historical record. (Backend from v0.47.0.)
- The host-file list moved out of **Live tools** (now motion-only) into the chooser, removing the
  duplication. `/analyze-file` now also accepts `max_smoothing` / `damping_ratio` so a local-file
  analysis honours the same knobs as an upload.

## [0.47.0] - 2026-06-03

### Added — Input Shaping: persistent on-host archive (backend, UX overhaul 4 of N)

- **A persistent archive of captures + generated configs.** New `shaper_archive` service +
  `/api/shaper/archive` routes keep recent resonance CSVs and generated `[input_shaper]`
  configs under `<data_dir>/input-shaper-archive/<run_id>/`, so results survive a reboot and
  the browser — reviewable, **downloadable**, and **deletable** as a historical record. A
  single `index.json` stores only a compact per-run summary (never the multi-thousand-element
  PSD / spectrogram arrays), and retention is bounded **per kind** (`FILAMIND_SHAPER_ARCHIVE_KEEP_N`,
  default 20) to stay light on the SD card.
- Routes: `GET /archive` (list), `GET /archive/{id}` (+ inline config), `GET /archive/{id}/file/{name}`
  (download), `DELETE /archive/{id}`, `POST /archive/save-config`, `POST /archive/save-file` (copy a
  host CSV in). All path-guarded (name regex + realpath containment), atomic writes.
- The browser UI for the archive (review / save / delete + the unified file source) lands next.

## [0.46.1] - 2026-06-03

### Changed — Input Shaping: per-tool motion confirm (UX overhaul, 3 of N)

- **Each on-printer tool now has its own "moves the toolhead — I'm ready" confirm.** Previously a
  single checkbox armed the live test, the belt comparison *and* axes-map together — so ticking it
  for a quick live test also armed the much larger belt sweep. The live test, belt comparison and
  axes-map are now three self-contained panels, each with its own confirm + run button (consistent
  with the Sustain and Vibrations panels). Safer and clearer; the shared concurrency lock and the
  backend print-guard are unchanged.

### Added

- Backend guard tests covering every on-printer entrypoint (live / belts / axes-map / sustain /
  vibrations / noise) refusing to run while the printer is printing.

## [0.46.0] - 2026-06-03

### Added — Input Shaping: built-in explanations + illustrations (UX overhaul, 2 of N)

- **The widget now teaches as it works.** A collapsed-by-default **"ℹ what's this?"** note sits
  beside each section — glossary (6 core terms), how to read the A–F grade, the frequency chart,
  the shaper table, the config block, and every live tool (noise / belts / axes-map / sustain /
  vibrations) plus a "guided vs. manual" primer. Each expands a short plain-language explanation
  and, where it helps, a **hand-drawn SVG illustration** (resonance peak, shaper impulses, belt
  pair, sensor axes, speed sweep, capture→analyze→apply flow). All copy lives in one `help.ts`,
  with the numbers anchored to the actual grading thresholds.
- The cryptic frequency-chart caption (`Hz · left PSD · right vibration reduction`) is replaced
  with plain wording (`frequency (Hz) → · solid = measured · faint = shaper leftover`).
- Collapsed by default, so the default view stays uncluttered.

## [0.45.0] - 2026-06-03

### Changed — Input Shaping: widget reorganized (UX overhaul, 1 of N)

- **Four clear views instead of six stacked toggles.** The Input Shaping widget now opens on a
  tab strip — **🧭 Guided** (the default landing view), **📈 Analyze**, **🔴 Live tools**,
  **🕘 History** — so only one task is on screen at a time instead of a long scroll of
  independently-toggled panels. The guided wizard is kept mounted, so an in-progress run
  (including its minutes-long on-printer captures) survives a tab switch. Behavior-preserving:
  every existing tool, the result view, and the combined `printer.cfg` block are unchanged —
  just better organized. First step of a multi-PR Input Shaping UX overhaul.
- **CI now fails on a stale `frontend/dist`.** The printer host serves the pre-built UI bundle
  straight from git, so a forgotten rebuild would silently ship an old UI. CI now runs
  `npm run build` and fails if anything under `frontend/dist` differs from what was committed.
  Added a matching PR-template reminder.

## [0.44.1] - 2026-06-03

### Docs — Shake&Tune feature parity complete (5 of 5)

- Documentation sweep closing out the Shake&Tune-parity effort (part 3/3): the ROADMAP
  gains phase 13 (vibrations profile) and the parity section is marked **✅ COMPLETE (5 of
  5)**; the Input Shaping range now reads v0.27.0 → v0.44.0. ARCHITECTURE updated to describe
  the full capture/analysis set (axes-map · sustain frequency · guided wizard · vibrations
  profile); the README feature list already covers it (v0.44.0). No code change.

## [0.44.0] - 2026-06-03

### Added — Input Shaping: vibrations profile UI + wizard (Shake&Tune parity, 5 of 5 — part 2/3)

- **Machine vibrations profile (browser).** A new 📊 panel in the "From the printer" view
  runs the sweep (with adjustable top speed + step) and renders it as a **speed-vs-energy
  curve** (smoothest bands highlighted, resonance speeds to avoid flagged, the recommended
  speed marked), a **polar plot** of vibration energy by travel direction, and an **angle ×
  speed heatmap** — plus the motor **symmetry**, the motor **resonant frequency / damping**,
  and a plain-language verdict. All dependency-free SVG.
- **Guided wizard: the Vibrations step is now measured.** What was a manual "did you see
  VFAs?" self-report now runs the real vibrations profile, gates on motor symmetry +
  low-frequency-noise health, and shows the same profile view inline with ranked
  recommendations (favour ~X mm/s, avoid the peak speeds, re-tension belts if symmetry is low).
  This closes the guided flow end to end: Noise → Belts → Shaper X → Shaper Y → Vibrations →
  Pressure.

## [0.43.0] - 2026-06-03

### Added — Input Shaping: vibrations profile backend (Shake&Tune parity, 5 of 5 — part 1/3)

- **Machine vibrations profile (backend).** New `POST /api/shaper/vibrations-profile` and a
  pure `vibrations_service` (a numpy port of Shake&Tune's `vibrations_computation.py`, reusing
  the vendored Klipper `ShaperCalibrate` for the per-segment PSD — no matplotlib, no Klipper
  host). It sweeps a range of speeds along each kinematic motor angle (0/90 for
  Cartesian/CoreXZ, 45/135 for CoreXY) while `ACCELEROMETER_MEASURE` brackets each constant-
  speed burst, then reports the **smoothest speed ranges**, the **resonance speeds to avoid**,
  the smoothest **travel directions** (polar energy), a motor **symmetry** score, and the
  **motors' resonant frequency + damping**. The whole sweep is one blocking call kept inside
  nginx's 1200s budget by a coarse default speed increment (finer increments take longer).
  Print-guarded; requires a configured resonance tester + accelerometer. The browser UI and
  the guided-wizard integration land in the next two releases.

## [0.42.1] - 2026-06-03

### Fixed

- **Long resonance tests no longer 504.** The nginx `/api/` proxy used the default 60s
  `proxy_read_timeout`, so any operation that moves the toolhead for more than a minute —
  a belt comparison (two full sweeps), a live test, axes-map, or sustain-frequency —
  returned **504 Gateway Timeout** even though the backend was still running and would have
  finished. Raised the `/api/` `proxy_read_timeout` / `proxy_send_timeout` to 1200s in both
  the installer (`scripts/install.sh`) and the deploy template. Added a UI note that live
  tests can take 1–5 minutes. (Existing installs: re-run the installer, or reload the
  updated nginx site, to apply.)

## [0.42.0] - 2026-06-03

### Added — Input Shaping: guided wizard completes the workflow (Shake&Tune parity, 4 of 5)

- The 🧭 guided wizard now covers the full Shake&Tune flow with two guided-manual steps
  after the shaper calibration: **Vibrations / VFAs** (a quick "do you see vertical fine
  artifacts?" self-report → keep slicer speeds out of the resonant band, or dig into TMC
  tuning) and **Pressure advance** (a copy-able PA tuning-tower g-code + how to apply the
  result). Frontend-only; the Vibrations step is the seam the measured vibrations profile
  (next) plugs into.

## [0.41.0] - 2026-06-03

### Added — Input Shaping: guided tuning wizard (Shake&Tune parity, 3 of 5)

- **🧭 Guided tune.** A step-by-step wizard that walks Noise → Belts → Shaper X → Shaper Y
  with automated **pass/fail gates** (reusing the existing scorers — the A–F grade, the belt
  verdict and the noise grade) and concrete **next-step suggestions** per result. A progress
  rail, per-step verdicts + ranked recommendation cards (do-now / consider / ok), and
  Next / Re-run / Skip controls; the X and Y captures flow into the same combined
  `[input_shaper]` block and the grade-tracked history. Pure, unit-tested `guided` (state +
  gates) and `recommend` modules; reuses the existing `/api/shaper/*` endpoints (no new
  backend).

## [0.40.0] - 2026-06-03

### Added — Input Shaping: sustain frequency (Shake&Tune parity, 2 of 5)

- **Hold-a-frequency hands-on diagnostic.** A new `🎯 sustain frequency` action buzzes the
  toolhead in place near a chosen frequency for a few seconds — a slow, narrow
  `TEST_RESONANCES` sweep, so **no custom macro or printer-config change is needed** — and
  you touch belts / toolhead / frame to feel which part is the resonance source. Returns a
  frequency×time **spectrogram** + an **energy-vs-time "touch timeline"** (the cyan dip marks
  when a touch reduced the vibration) + a verdict on whether the requested frequency
  dominated. New backend `POST /api/shaper/excitate` (moves the toolhead in place;
  print-guarded). Pure-numpy STFT in `spectrogram_service`.

## [0.39.0] - 2026-06-02

### Added — Input Shaping: axes-map calibration (Shake&Tune parity, 1 of 5)

- **Accelerometer orientation detection.** A new `🧭 axes map` action jogs the toolhead
  ~30 mm in +X/+Y/+Z, integrates the accelerometer signal to velocity, and detects the
  Klipper `axes_map` to use (e.g. `-z, y, x`) plus per-axis tilt + confidence — so every
  Input Shaping graph reads with X/Y/Z aligned. Reconstructs the no-signal axis on 2-axis
  / bed-slinger machines. Shows a paste-ready `[<chip>] axes_map: …` (Copy) + a
  "matches your config?" verdict + a velocity-sequence chart.
- New backend `POST /api/shaper/axes-map` (**moves the toolhead**; print-guarded; auto-homes).
  The pure-numpy detection (`axes_map_service`) is ported from Shake&Tune's
  `axes_map_computation` (GPL-3.0); the capture is orchestrated over Moonraker REST with
  `ACCELEROMETER_MEASURE` bracketing the moves — the reusable capture spine for the coming
  sustain-frequency and vibrations features.

## [0.38.1] - 2026-06-02

### Fixed

- **Portable Mainsail sidebar link.** The installer hard-coded the sidebar link to
  `http://<hostname>.local:8090`, which is dead for any client that can't resolve mDNS
  (Windows without Bonjour, Android, a different subnet, VPN) — a real user saw it land
  on an unreachable `…​.local:8090`. It now defaults to the primary **LAN IP** (resolves
  everywhere on the network), opens in a new tab, and accepts a `FILAMIND_PUBLIC_HOST`
  override (`FILAMIND_PUBLIC_HOST=printer.example` or a fixed IP). The app itself was
  always fine — same-origin — so the broken case was purely the link host. (A fully
  host-preserving subpath link, working at *any* address, is the next step.)

## [0.38.0] - 2026-06-02

### Added

- **Grade-tracked calibration history.** The Input Shaping history now records the
  measurement quality grade (A–F + score) for each calibration and shows it inline,
  with a trend arrow (▲ improved / ▼ declined) versus the previous test of the same
  axis — so the effect of a mechanical fix on measurement quality is visible at a
  glance. Frontend-only; entries saved before v0.38 (without a grade) still load.

## [0.37.0] - 2026-06-02

### Added

- **CoreXY belt comparison.** A `🟰 compare belts` action in the Input Shaping "from the
  printer" panel runs a resonance test along each belt diagonal — `(1,1)` and `(1,-1)` —
  and overlays the two responses with a verdict (belts matched vs a tension mismatch,
  judged from the dominant-peak frequencies), so you can balance CoreXY belt tension.
  New backend route `POST /api/shaper/compare-belts` (print-guarded; **moves the
  toolhead**, two sweeps).

## [0.36.0] - 2026-06-02

### Added

- **Accelerometer noise pre-check.** A motion-free `MEASURE_AXES_NOISE` button in the
  Input Shaping "from the printer" panel reads the accelerometer's idle noise floor and
  grades it (quiet / elevated / too noisy — Klipper's normal range is ~1-100), so you
  can validate the sensor mount before running a resonance test. New backend route
  `POST /api/shaper/noise` (print-guarded; does **not** move the toolhead).

### Documentation

- Brought the docs in step with the shipped features: documented the **Input Shaping**
  widget in `README.md` + `ROADMAP.md`, refreshed the version badge, filled in the
  `/api/shaper/*` endpoints and the firmware / resonance `FILAMIND_*` settings in
  `backend/README.md`, refreshed `docs/ARCHITECTURE.md`, and added a "keep docs in step
  with features" rule to `CONTRIBUTING.md`.

## [0.35.0] - 2026-06-02

### Added — Input Shaping advanced insights

- **Measurement quality grade (A–F).** Each capture gets a letter grade + a 0–100
  score from five factors — peak clarity (signal-to-noise), residual vibration,
  smoothing, frequency band, and single-vs-multi resonance — with a per-factor
  breakdown and a plain verdict, so a trustworthy, well-tuned result is obvious at a
  glance from one that needs a re-test.
- **Visual diagnostics + fixes.** Rule-based cards map the measurement to the likely
  mechanical cause and the fix, each with a hand-drawn, dependency-free SVG
  illustration: low frequency → tighten belts / stiffen frame; high smoothing →
  retune; multi-hump → re-seat the toolhead; weak peak → secure the accelerometer;
  plus a cross-axis card that flags a large X-vs-Y stiffness mismatch once both axes
  are captured.
- **Annotated frequency-response chart.** The dominant resonance peak is marked
  (vertical line + dot + a "57 Hz" label) and the PSD noise floor is drawn as a faint
  reference line, so the meaningful peak stands out from the noise.
- The **Recommended** banner now shows the suggested `max_accel`.

### Changed

- The plain-text hint list is replaced by the richer grade + diagnostics. The
  `interpret` helper is superseded by pure, unit-tested `grade` + `diagnose` modules.

## [0.34.0] - 2026-06-02

### Changed / Fixed — portability (works for any user on any printer, not just the dev's)

- **Import finds resonance CSVs beyond `/tmp`.** Default scan dirs are now
  `/tmp,~/printer_data/config,~/printer_data/config/input_shaper` (override with
  `FILAMIND_RESONANCE_DIRS`), so captures saved by the usual input-shaper flows show
  up — not just the volatile `/tmp` (which is wiped on reboot and empty off-host).
- **Large live captures are no longer silently truncated.** The host-file read cap
  was 20 MB; a long sweep exceeds that (a real SV08 capture was 30 MB), feeding the
  parser a truncated file. Raised to 128 MB.
- **Deploy templates are consistent + host-portable.** The nginx site, the Mainsail
  `navi.json` and the deploy docs used port 8080 while `install.sh` uses 8090 —
  aligned to 8090. Removed the misleading advice to bake `VITE_*` host URLs into the
  build: the pre-built UI resolves Moonraker/backend/Mainsail from `window.location`
  (same origin), so it already works at whatever IP/hostname you reach it by — no
  host is baked in. (A fully host-preserving Mainsail sidebar link via a subpath
  reverse-proxy is the documented next step.)

## [0.33.4] - 2026-06-02

### Fixed

- **Live resonance test failed to parse the captured CSV** ("the number of columns
  changed from 4 to 2"). Klipper writes the raw accelerometer data from a
  background process, so `TEST_RESONANCES` returns before the (often hundreds of
  thousands of rows) file is fully flushed — the analysis read it mid-write and
  hit a truncated final row. The live test now waits for the file size to
  stabilise before reading it, and the raw-CSV parser tolerates a ragged row.

## [0.33.3] - 2026-06-02

### Fixed

- **Live resonance test failed with "Must home axis first".** `TEST_RESONANCES`
  moves the toolhead to the probe point, which needs homed axes. The live test now
  homes the printer (`G28`) first when it isn't already fully homed, then runs the
  test — so the button works from cold.

## [0.33.2] - 2026-06-02

### Fixed

- **Live resonance test wrongly reported "No `[resonance_tester]`".** The guard
  looked for `resonance_tester` in `/printer/objects/list`, but that's a Klipper
  config *section*, not a queryable status object — it never appears there, so the
  live test always refused, even on printers that have it configured (e.g. a Sovol
  SV08 with its toolhead ADXL345). It now checks the parsed `configfile` config,
  where the section actually lives.

## [0.33.1] - 2026-06-02

### Fixed

- **Input Shaping analysis 500'd when `numpy` was missing from the backend venv.**
  A manual `git reset` deploy doesn't run `pip install`, so a host that never ran
  `deploy/install-host.sh` (or the Moonraker update manager) lacked numpy and every
  analysis failed with an unhandled HTTP 500. The shaper helper is now built inside
  the guarded block, so a missing dependency surfaces as a clear 400 instead. (The
  real fix is installing the dependency — run `install-host.sh` / the update
  manager after pulling new backend requirements.)

## [0.33.0] - 2026-06-02

### Added

- **Input Shaping — connected to the printer.** A new "from printer" panel:
  - **Import** the resonance CSVs Klipper already wrote on the host (scans `/tmp`
    by default) and analyse one with a click — no download/re-upload.
  - **Run a live test** — trigger `TEST_RESONANCES` on a chosen axis via Moonraker
    (gated behind a "moves the toolhead" confirm), then auto-analyse the captured
    CSV. Print-guarded; refuses unless a `[resonance_tester]` is configured.

  Backend: `GET /api/shaper/files`, `POST /api/shaper/analyze-file` (path-validated
  to the configured `resonance_dirs`), `POST /api/shaper/live-test`, and
  `MoonrakerClient.run_gcode`. The connected paths are verified locally with a
  mocked Moonraker; running an actual live test needs a printer with an
  accelerometer.

### Added

- **Input Shaping — interpretation hints + calibration history.** Each analysis now
  comes with plain-language guidance: the suggested `max_accel`, warnings for a low
  shaper frequency or high smoothing, and a note when a multi-hump shaper is
  chosen. A browser-local **history** records each calibration (date · axis ·
  shaper @ frequency) so you can watch how an axis drifts over time. Completes the
  Input Shaping widget (phases 1–6).

## [0.31.0] - 2026-06-02

### Added

- **Input Shaping — compare two captures (A ⇄ B).** A new compare panel: load two
  resonance CSVs (e.g. before/after a belt-tension fix, or the same axis re-tested)
  and see them side by side — an overlaid total-PSD chart plus a metric table
  (recommended shaper, frequencies, peak frequency, remaining vibrations,
  `max_accel`) that flags whether **B improved or regressed** versus A.

## [0.30.0] - 2026-06-02

### Added

- **Input Shaping — per-axis X/Y config + advanced parameters.** Analyze the X and
  Y resonance files in turn and the widget accumulates both into a single
  `[input_shaper]` block (`shaper_type_x` / `_y` + frequencies), with chips showing
  which axes are captured and a clear button. A new **advanced** panel exposes the
  knobs the desktop tool hardcodes — `max_freq`, `scv`, `max_smoothing`,
  `damping_ratio` (blank = Klipper's default).

## [0.29.0] - 2026-06-02

### Added

- **Input Shaping — frequency-response chart.** The widget now draws the resonance
  **frequency-response graph** inline as a dependency-free SVG: the X / Y / Z and
  combined PSD curves layered over each shaper's vibration-reduction curve, with
  the recommended shaper accented and the rest dashed — the same picture as
  Klipper's `calibrate_shaper` plot, rendered in the browser.

## [0.28.0] - 2026-06-02

### Added

- **Input Shaping widget (analysis UI).** A new **Input Shaping** sidebar page:
  upload a resonance `.csv`, pick the axis, and Analyze → it shows the recommended
  shaper (e.g. `MZV @ 52.3 Hz`), a table of every tested shaper (frequency,
  remaining vibrations, smoothing, suggested `max_accel`), and a ready-to-paste
  `[input_shaper]` config block with one-click copy. The frequency-response chart
  lands next.

## [0.27.0] - 2026-06-02

### Added

- **Input Shaping — resonance analysis backend.** A new `POST /api/shaper/analyze`
  endpoint runs Klipper's own input-shaper calibration on an uploaded resonance
  CSV (a PSD `freq,psd_x,…` file or raw accelerometer `time,accel_x,…` samples)
  and returns the recommended shaper, every tested shaper's metrics (frequency,
  remaining vibrations, smoothing, suggested `max_accel`), and the full
  frequency-response series for plotting. The math is Klipper's `shaper_calibrate`
  vendored under `backend/app/vendor/klipper_shaper` (GPLv3); it runs serially
  with only numpy, so no printer is required. First slice of the Input Shaping
  widget.

## [0.26.0] - 2026-05-31

### Added

- **Compare two external firmware files side by side.** A `compare A ⇄ B` picker
  at the top of the External firmware section diffs the two files' detected
  properties — app, version, MCU, size, and every baked-in `config` constant —
  into a read-only table that highlights what **changed**, what's **only in A**,
  what's **only in B**, and what's the **same** (with a per-config-key tally). The
  diff runs entirely client-side from the already-inspected properties, so it
  needs no extra request and never touches the files. Appears once two files are
  registered.

### Added

- **External firmware shows the full build config baked into the file (read-only).**
  Beyond the Klipper version, the inspector now decompresses the firmware's data
  dictionary and surfaces every constant compiled into the binary — `MCU`,
  `CLOCK_FREQ`, the reserved USB / SPI / I2C bus pins, `STEPPER_BOTH_EDGE`,
  `ADC_MAX` / `PWM_MAX`, … — in a collapsible, read-only list under each file
  (e.g. an SV08 `.bin` reveals its 14 baked-in settings). These are compiled into
  the machine code and **cannot be edited**: to change them, build a profile in
  Configure and flash that instead — the panel says so explicitly rather than
  implying the values are editable.

## [0.24.1] - 2026-05-31

### Fixed

- **External firmware reads the version from raw `.bin` files too.** Klipper
  stores its version / MCU in a **zlib-compressed data dictionary**, not plain
  strings, so a raw `.bin` (e.g. an SV08 firmware) showed nothing. The inspector
  now decompresses that dictionary (→ `v0.12.0-… · stm32f103xe`).

## [0.24.0] - 2026-05-31

### Changed

- **Optional config options show as normal toggles (no lock).** Klipper's
  "Optional features (to reduce code size)" (`WANT_*`) are gated behind
  `HAVE_LIMITED_CODE_SIZE`, which Klipper auto-selects only for MCUs with **<64 KB
  flash** (`select … if FLASH_SIZE < 0x10000`). They now render as plain toggles,
  matching the reference tool: on flash-limited boards they apply; on roomier
  boards Klipper auto-includes them. (Reverts the 🔒 lock from v0.21.2.)

### Added

- **External firmware: read embedded properties.** On upload (and for existing
  files), the binary is scanned for its embedded **Klipper version** and an **MCU
  hint**, shown read-only ("🔍 read from file: Klipper v… · mcu …").

## [0.23.1] - 2026-05-31

### Fixed

- **External firmware section no longer freezes the page.** The per-file
  flash-target state was created lazily inside a `v-model` during render, which
  looped the renderer once a firmware entry existed. It's now seeded when the
  list loads.

## [0.23.0] - 2026-05-31

### Added

- **External firmware section.** A new section in the Devices manager to register
  pre-built firmware files (`.bin` / `.uf2` / `.elf` / `.hex`) and flash them
  directly — no build step. Upload a file, edit its flash properties (label,
  flash method, bootloader offset, CAN interface, notes), pick a target board,
  and flash; files can also be downloaded or removed. Backed by new
  `/api/firmware/external` endpoints.

## [0.22.0] - 2026-05-31

### Added

- **Per-device Katapult toggle.** Each serial / CAN device in the Devices manager
  now has a **katapult** checkbox (the flag was stored but never surfaced). When
  it's off, a flash **skips the Katapult reboot-to-bootloader** step — for boards
  flashed directly or via `make flash` — matching how the reference tool models
  Katapult per device.

## [0.21.2] - 2026-05-31

### Fixed

- **"Optional" options that can't be set now show as locked.** Turning on the
  *optional* toggle surfaces Klipper's `WANT_*` feature flags; many depend on a
  prerequisite that isn't enabled in the current configuration, so Klipper won't
  let them change. They now render **🔒 locked** (with an explanatory tooltip)
  instead of an ON toggle that did nothing when clicked.

## [0.21.1] - 2026-05-31

### Fixed

- **Config options are easier to toggle.** A bool option's **whole row** is now a
  click target (not just the small badge on the right), with a pointer cursor and
  a hover highlight — so options like *Optimize stepper code…* are obviously and
  reliably controllable. Options that Kconfig locks (forced by another symbol)
  now show a 🔒 and a tooltip explaining why they can't be changed.
- **Browsers always load the latest build.** nginx now serves `index.html` with
  `Cache-Control: no-cache` (and the content-hashed assets as `immutable`), so a
  new deploy is picked up immediately instead of a stale bundle lingering in the
  browser cache.

## [0.21.0] - 2026-05-31

### Added

- **Discovered boards show their bootloader mode** — the Devices manager's
  *Discovered* list now badges each unregistered board with its live mode /
  bootloader (KATAPULT, READY, DFU, …), and no longer offers the Linux host MCU
  as an addable board (it is managed separately).

### Changed

- **Linked bootloader identities are clearer** — a board's attached Katapult /
  DFU identity now renders as an indented, connected sub-card with an *unlink*
  button, instead of a flat badge row; the discovered-board action is labelled
  **🔗 link**.
- **Firmware configurator shows the whole config** — the Kconfig editor no longer
  scrolls inside a fixed-height box; every option is visible and the page scrolls
  normally.

## [0.20.1] - 2026-05-31

### Fixed

- **Configurator no longer 500s when switching processor architectures** (STM32,
  ATSAM, LPC176x, RP2040, PRU, AR100). Those architectures expose Kconfig **menu /
  comment** nodes, which — unlike symbols — have no `help` attribute in
  kconfiglib; reading it raised `AttributeError`. The serializer now reads it
  safely. (Surfaced by v0.18.0 forcing the low-level menus visible.)

## [0.20.0] - 2026-05-31

### Added

- **Inline help** — a *help* toggle renders each option's help text under it
  (previously only a hover tooltip).
- **Profile Info card** — the selected profile's built status, version, and flags
  (linux / avr / CAN bridge) at a glance.
- **Raw symbol names** — a *raw* toggle shows the underlying Kconfig symbol name
  and, for gated options, the dependency that controls them.
- **Kconfig comments** are now rendered in the editor (informational notes that
  were previously dropped).
- Each symbol now carries its **default** value and **dependency** expression,
  surfaced as inline hints under the *raw* / *help* toggles.

### Fixed

- **Read-only options can't be edited.** Symbols selected by another option now
  also disable their dropdown / text field (only the on/off toggle was guarded).

## [0.19.0] - 2026-05-31

### Added

- **Rename a profile** — renames its `.config`, moves any built binary +
  build-info, and rewrites every device that pointed at it, in one step.
- **Duplicate / save-as a profile** — copies a profile's config (and any built
  binary) under a new name to branch from an existing setup.

### Changed

- **Build auto-saves pending edits** — clicking *build* with unsaved Kconfig
  edits now saves them into the profile first, so the compiled firmware always
  reflects what's on screen.

## [0.18.1] - 2026-05-31

### Fixed

- **Downloaded firmware keeps its real filename for profiles with spaces.** The
  ↓ .bin download parsed only the plain `Content-Disposition` form, so a profile
  like "Linux host" (sent by Starlette as the RFC 5987 `filename*=utf-8''…` form)
  fell back to a wrong `.bin` name. It now decodes both forms (→ `Linux host.elf`).

## [0.18.0] - 2026-05-31

### Added

- **Configurator: low-level options are always visible.** The firmware config
  editor now force-enables Klipper's `LOW_LEVEL_OPTIONS` (and
  `HAVE_LIMITED_CODE_SIZE`) gates, so the optimization / low-level menus Klipper
  hides by default always show. Revealed options keep their defaults — a build
  is unchanged unless you edit one.
- **Download the built firmware binary.** Built profiles get a **↓ .bin** button
  (backed by `GET /api/firmware/config/profiles/{name}/artifact`) to download the
  compiled `.bin` / `.uf2` / `.elf` for manual flashing.

### Changed

- README refreshed — it described an "empty scaffold"; it now documents the
  shipped Firmware Upgrade widget.

## [0.17.1] - 2026-05-31

### Fixed

- **Update alert compares the right versions** — a device's **⚠ update** badge
  now compares its **live MCU firmware** (what Moonraker reports the board
  running) against the **host's running Klipper** (`software_version`), instead
  of the repo build version. Both come from the live printer, matching how
  Klipper itself decides host↔MCU sync.

### Added

- Roadmap **Phase 14 — Configurator / profile parity**, capturing the
  profile-creation gaps found vs the reference (rename, duplicate / save-as,
  download the built binary, forced low-level symbols, inline help text, …).

## [0.17.0] - 2026-05-31

### Added

- **Sidebar pages** — the FilaMind sidebar now lists each panel (e.g. **Firmware
  Upgrade**) as its own entry; clicking it opens that panel on its own page. The
  **Dashboard** home is intentionally empty for now, ready for future widgets.
- **Per-device "build & flash"** — a third button on each device card builds the
  assigned profile then flashes it in one go (it only flashes if the build
  succeeded).
- **Outdated-firmware alert** — a device card shows a **⚠ update** badge when its
  flashed firmware differs from the host's Klipper version.

## [0.16.2] - 2026-05-31

### Fixed

- **Per-device flash runs the built firmware directly** — clicking **flash** on a
  device card now flashes its assigned profile (reusing the artifact you just
  built) instead of opening a separate profile-picker. The streamed command log
  appears **right under that device's build / flash buttons**, and the batch log
  under the batch buttons.

## [0.16.1] - 2026-05-31

### Changed

- Slimmed the main screen — removed the per-MCU status rows and the Linux host
  MCU row; the operational **Devices** cards now carry each board's live status.
  The host Klipper row, tool / setup badges, services, and Devices section stay.

## [0.16.0] - 2026-05-31

### Changed

- **Operational dashboard** — your registered devices now live on the **main
  screen** as operational cards (live status, profile, version, per-device
  **build / flash / boot**), and the **batch** buttons (Build all / Flash all /
  Flash ready / Build & flash) moved there too. A device appears on the main
  screen only once it's been **added and given a profile**, so raw discovery no
  longer duplicates there. The **Devices manager** (the former Devices tab) is
  now purely for discovering, adding, and configuring boards.

## [0.15.0] - 2026-05-31

### Added

- **Health & install integrity (Phase 13)** — a new `/firmware/health` check
  reports whether the host is set up for flashing (the passwordless **sudo**
  rule, the **STM32 DFU udev rule**, and **dfu-util**), shown as a **setup**
  badge with a fix-it tooltip. `deploy/setup-sudoers.sh` now also installs a
  `99-stm32-dfu.rules` udev rule so **DFU flashing works without sudo**. This
  completes the Firmware Upgrade widget's planned phases (1–13).

## [0.14.0] - 2026-05-31

### Added

- **Backup & restore (Phase 12)** — **export** the device registry + every
  Kconfig profile as a single portable ZIP, and **import** it back. Firmware
  binaries are excluded (they rebuild from the profiles), and restore is hardened
  against zip path-traversal (only `devices.json` + validated profile names are
  written). Export / import live in the Devices view.

## [0.13.0] - 2026-05-31

### Added

- **Beacon (Phase 11)** — FilaMind now detects connected **Beacon eddy-current
  probes** and updates their firmware through the Beacon plugin's own
  `update_firmware.py` (located via Moonraker's update_manager). The widget shows
  each probe with its revision, the version available in the plugin checkout, and
  a **flash** button — and only appears when a probe is present.

## [0.12.0] - 2026-05-31

### Added

- **Advanced flash (Phase 10)** — sturdier flashing for more boards: DFU now
  **retries** (up to 3×) and **exits via `:leave`** to return to firmware; a
  **USB-to-CAN bridge** (a CAN board that enumerates as a serial path) is flashed
  over serial automatically; a serial board that **re-enumerates** under a new
  `/dev` id after flashing is matched and its registry entry updated; and a board
  can be rebooted straight into **STM32 DFU** with a 1200-baud touch (a new
  **dfu** button beside **boot**).

## [0.11.0] - 2026-05-31

### Added

- **Live status & services (Phase 9)** — the widget now **auto-refreshes**
  every few seconds, so each board's live mode (service / ready / dfu / offline)
  stays current. A new **Services** bar lists the host's Klipper / Moonraker
  units and can **start / stop / restart** them all (ordered so host MCUs come
  up first and go down last). Each saved board gains a live-mode badge and a
  **boot** button that reboots it into its Katapult bootloader.

## [0.10.0] - 2026-05-31

### Added

- **Batch operations (Phase 8)** — build and/or flash every device in one go:
  **Build all**, **Flash all**, **Flash ready** (only boards already sitting in
  a bootloader), and **Build & flash**. It runs as a cancellable background task
  with a live, colorized log; **cancel** stops it at the next checkpoint. Builds
  are de-duplicated by profile, `exclude_from_batch` devices are skipped, and
  each flash reuses the same guarded single-board sequence (print-lock, sudo,
  bootloader reboot, version recording).

## [0.9.1] - 2026-05-31

### Changed

- Settled the Phase 7 registry's public surface on **Devices**: the
  `/api/firmware/devices` (+ `/devices/attach`) endpoints and the `devices.json`
  store. Anyone who integrated against the v0.9.0 paths should update them.

## [0.9.0] - 2026-05-31

### Added

- **Devices (Phase 7)** — FilaMind now keeps a saved device registry
  (`devices.json`): each board remembers its build profile, how it is flashed
  (method, baudrate, CAN interface), free-form notes, an exclude-from-batch
  flag, an optional custom make command, and the separate Katapult / DFU
  **bootloader identity** it takes on while flashing. A new **Devices** view
  lists registered boards (editable inline), **adds** a discovered board, and
  **attaches** a found bootloader device to an existing entry. Board discovery
  now flags which boards are already `managed`.

## [0.8.0] - 2026-05-31

### Added

- **Firmware version tracking (Phase 6)** — FilaMind now captures the Klipper
  version / commit / date a profile is built with (`<profile>.build_info.json`
  via `get_klipper_version`) and records what it flashes to each board
  (`flashed.json`). The **Linux host MCU** and other boards now show their
  firmware version even when Moonraker can't report it (e.g. an unconfigured
  host MCU) — and each profile carries its `built_version`. Closes the
  host-MCU version-display gap.

## [0.7.1] - 2026-05-31

### Changed

- The **Linux host MCU** flash now matches the standard install: stop
  `klipper-mcu`, free the binary with `fuser -k`, install it executable, restart
  the service, and wait for it to come up — warning (instead of leaving it
  silently broken) if the kernel blocks realtime, in which case the `-r` flag
  should be dropped from the klipper-mcu unit. `setup-sudoers.sh` now also grants
  `fuser`.

## [0.7.0] - 2026-05-31

### Added

- **Live MCU telemetry** in the firmware status — each MCU now shows its actual
  clock frequency, awake load, and retransmitted-bytes count (the key host↔MCU
  comms-health signal, highlighted when non-zero), pulled from the MCU's
  `last_stats`. First of the Firmware Upgrade widget's planned enhancements.

## [0.6.2] - 2026-05-31

### Fixed

- The flash readiness probe ran `sudo -n true`, which never matches the narrow
  sudoers rule, so flashing kept reporting "blocked" even after running
  `setup-sudoers.sh`. It now probes an allowed command (`systemctl --version`).

## [0.6.1] - 2026-05-31

### Added

- `deploy/setup-sudoers.sh` — grants the backend the narrow passwordless-sudo
  rights flashing needs (`systemctl`, `dfu-util`, `cp`, `chmod`). Run once with
  sudo to enable the Flash phase; until then the UI reports flashing as blocked
  and points to this script.

### Fixed

- Flash now stops/starts the correct service (`klipper-mcu` for a Linux-process
  MCU, `klipper` for hardware MCUs) and marks an installed Linux MCU binary
  executable.

## [0.6.0] - 2026-05-31

### Added

- **Firmware flash (Phase 5 — Flash)**: push a built artifact onto a board from
  the browser. `POST /api/firmware/flash` runs the right tool for the board —
  Katapult `flashtool.py` (serial / CAN), `dfu-util` (DFU), or `make flash`
  (AVR) — rebooting it to its bootloader first, and streams the log. A read-only
  `POST /api/firmware/flash-plan` previews the exact command + safety gates.
  Flashing is **refused while a print is running**, requires a built artifact,
  and needs passwordless sudo; the UI shows the plan, warnings, and a hard
  confirmation before anything touches the board. Completes the widget's
  configure → build → flash pipeline.

## [0.5.0] - 2026-05-31

### Added

- **Firmware build (Phase 4 — Build)**: compile a saved profile into a flashable
  artifact from the browser. `GET /api/firmware/build/{profile}` stages the
  profile's `.config`, runs `make clean` + `make olddefconfig` + `make`, and
  **streams the build log live** (with stall / total timeouts); the resulting
  `out/klipper.{bin,uf2,elf}` is copied into the artifacts directory under the
  profile name. The Configure view gains a **build** button per profile, a live
  log console, and a **built ✓** indicator.

## [0.4.0] - 2026-05-31

### Added

- **Firmware config editor (Phase 3 — Configure)**: edit Klipper's
  `make menuconfig` options from the browser. The backend loads Klipper's bundled
  `kconfiglib`, serialises `src/Kconfig` into a live menu tree (dependencies
  re-evaluate as values change), and writes a `.config`. Edits are saved as
  **per-board profiles** (one `.config` each) under the FilaMind data dir, with
  list / save / delete via `GET`/`POST`/`DELETE /api/firmware/config/...`. The
  widget gains a **Configure firmware** view that renders the tree as a form with
  a profile selector. Adds a `kconfiglib` dependency (Klipper's own copy is
  preferred at runtime).

## [0.3.0] - 2026-05-31

### Added

- **Board discovery** (`GET /api/firmware/boards`) — finds every flashable MCU on
  any printer by merging four independent sources: configured `[mcu]` sections
  from Moonraker, USB/serial (`/dev/serial/by-id` + ttyACM/ttyUSB), CAN (Katapult
  `flashtool.py -q` on each CAN interface), and DFU (`dfu-util -l`). Each board
  reports its connection (usb/can/dfu/linux), mode (service / ready / dfu),
  whether it is configured, and its running firmware version. Surfaced as a
  **Detected boards** section in the Firmware Upgrade widget.

## [0.2.2] - 2026-05-31

### Added

- Firmware Upgrade widget now surfaces the optional **Linux host MCU** (Klipper
  "Linux process" MCU) explicitly — `active` / `available · not configured` /
  `not installed` — based on the host's `klipper-mcu` service and whether a host
  MCU is wired into the running config. Each MCU row also shows its connection
  kind (host / canbus / usb / serial).

## [0.2.1] - 2026-05-31

### Changed

- Firmware Upgrade widget: the **host** is now shown as a first-class row in the
  device list — the reference version every MCU is compared against — styled
  distinctly instead of a separate header line.

## [0.2.0] - 2026-05-31

### Added

- **Firmware Upgrade widget — Phase 1**: read-only firmware status showing each
  MCU's version, host↔MCU sync detection, and toolchain readiness
  (`GET /api/firmware/status`). The first FilaMind widget.
- A living [`ROADMAP.md`](ROADMAP.md).
- Dev test harness (`dev/virtual-printer/`): develop against any Moonraker through
  the Vite dev proxy via `MOONRAKER_PROXY_TARGET` (strips the browser Origin, so no
  printer CORS changes are needed) — plus an optional Docker simulated printer.
- Verified the full on-device deployment on a real **BigTreeTech CB1**: backend
  systemd service + nginx-served UI + a **FilaMind Flow entry in the Mainsail
  sidebar**, with klippy `ready` and a live Connected badge.

### Changed

- The frontend now defaults to **same-origin** endpoints (it is served behind a
  proxy that forwards Moonraker/backend traffic) instead of `host:7125`, so no host
  or port is baked into the build and there is no CORS.
- The deploy nginx template strips `Origin` on the Moonraker proxy.
- Relicensed from MIT to **GPL-3.0-or-later** to match the Klipper / Moonraker ecosystem.
- Header now has a **Back to Mainsail** button.

### Fixed

- Backend `cors_origins` raised a `SettingsError` when set from the environment; it
  is now a comma-separated string exposed as `cors_origin_list`.

## [0.1.0] - 2026-05-31

### Added

- Project scaffold (empty, no feature widgets yet).
- Frontend: Vue 3 + Vite + TypeScript + Tailwind CSS with a Neo-Brutalist design
  system (tokens + `nb-card` / `nb-btn` / `nb-badge` components).
- `MoonrakerClient`: reconnecting JSON-RPC WebSocket client with request
  correlation, notification fan-out, and automatic subscription restoration.
- Widget registry (extensibility core) + Pinia printer store + app shell
  (sidebar, header, live connection status, empty-state dashboard).
- Backend: FastAPI service with health and Moonraker reachability endpoints,
  settings via `pydantic-settings`, and a server-side Moonraker HTTP client.
- Tooling: ESLint (flat) + Prettier + Vitest; Ruff + Mypy + Pytest; GitHub
  Actions CI; deployment templates (systemd, nginx, Moonraker update_manager,
  Mainsail navi).

[Unreleased]: https://github.com/filamind-app/filamind-flow/compare/v0.24.1...HEAD
[0.24.1]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.24.1
[0.24.0]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.24.0
[0.23.1]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.23.1
[0.23.0]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.23.0
[0.22.0]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.22.0
[0.21.2]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.21.2
[0.21.1]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.21.1
[0.21.0]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.21.0
[0.20.1]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.20.1
[0.20.0]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.20.0
[0.19.0]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.19.0
[0.18.1]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.18.1
[0.18.0]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.18.0
[0.17.1]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.17.1
[0.17.0]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.17.0
[0.16.2]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.16.2
[0.16.1]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.16.1
[0.16.0]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.16.0
[0.15.0]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.15.0
[0.14.0]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.14.0
[0.13.0]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.13.0
[0.12.0]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.12.0
[0.11.0]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.11.0
[0.10.0]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.10.0
[0.9.1]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.9.1
[0.9.0]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.9.0
[0.8.0]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.8.0
[0.7.1]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.7.1
[0.7.0]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.7.0
[0.6.2]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.6.2
[0.6.1]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.6.1
[0.6.0]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.6.0
[0.5.0]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.5.0
[0.4.0]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.4.0
[0.3.0]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.3.0
[0.2.2]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.2.2
[0.2.1]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.2.1
[0.2.0]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.2.0
[0.1.0]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.1.0
