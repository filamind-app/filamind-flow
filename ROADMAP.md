# FilaMind Flow — Roadmap

A living roadmap — updated as features land. Each feature ships on its own branch
→ Pull Request → tagged release.

**Legend:** ✅ done · 🚧 in progress · 📋 planned

## Widgets

### ✅ Firmware Manager

Configure, build, flash and upgrade the firmware on every MCU of your printer —
from the browser, no command line. **The core pipeline (phases 1–5) is complete.**
Phases 6+ grow it into a full multi-board manager.

| Phase | Scope | Risk |
| ----- | ----- | ---- |
| ✅ **1 — Foundation** | Firmware status: per-MCU versions, host↔MCU sync check, tool readiness, Linux host MCU | low (read-only) |
| ✅ **2 — Discover** | Detect every board on any printer — Moonraker `[mcu]` + USB / CAN / DFU scans, with connection + mode | low (read-only) |
| ✅ **3 — Configure** | Web Kconfig editor (reactive form) + saved per-board profiles | medium |
| ✅ **4 — Build** | Compile firmware for a profile, with live streamed log | medium |
| ✅ **5 — Flash** | Flash via Katapult / DFU / `make flash`, reboot-to-bootloader, safety guards (print-lock, sudo, confirm) | high (touches hardware) |

**Next phases — toward a full multi-board manager**

| Phase | Scope | Closes / unlocks |
| ----- | ----- | ---------------- |
| ✅ **6 — Version tracking** | Capture Klipper version/commit/date at build time (`<profile>.build_info.json` + `get_klipper_version`); show the **built / flashed version** on every board — including the Linux host MCU, which Moonraker can't report | the reported "host MCU shows no version" gap |
| ✅ **7 — Devices (persistence)** | A saved device registry (`devices.json`): board↔profile mapping, flashed_version, last_flashed, per-device settings (baudrate, custom make command, exclude-from-batch, notes), and a **dual identity per device** (runtime + its separate Katapult-serial / DFU bootloader id); **Add / Attach / Remove** discovered hardware (Attach binds a found bootloader device to an existing entry) | a persistent dashboard + everything below |
| ✅ **8 — Batch operations** | Build All / Flash All / Flash Ready across all devices, with service stop/start orchestration; **cancel a running build/flash** (task store) + colorized / expandable log panel | one-click upgrade of every board |
| ✅ **9 — Live status & services** | Live per-device status (service / ready / offline / dfu) with **auto-refresh polling**; a **Services** bar to start/stop/restart Klipper / Moonraker; **reboot a board into its Katapult bootloader** (Restart-to-Firmware / Reboot-to-DFU land with the Phase 10 wire-protocol) | interactive dashboard |
| ✅ **10 — Advanced flash** | 1200bps magic-baud reboot-to-DFU, DFU **retry + `:leave`** auto-exit, **USB-to-CAN bridge** redirect, AVR auto-detect, **post-flash re-enumeration** (new `/dev` id after flash → auto-update the registry). (Test-DFU-Cycle validation + Katapult native wire-protocol return-to-firmware remain follow-ups.) | reliability on more boards |
| ✅ **11 — Beacon** | Beacon eddy-probe firmware (detect probes + flash via the plugin's `update_firmware.py` + show the available version) | Beacon users |
| ✅ **12 — Backup & Restore** | Export / import a ZIP of the **device registry + all Kconfig profiles** (binaries excluded, rebuildable; restore guards against zip path-traversal) | migrate or recover a whole setup |
| ✅ **13 — Health & install integrity** | `/firmware/health` checks (sudoers, **udev DFU rule**, sudo-ready, dfu-util) + a UI **setup** badge with fix-it hints; `deploy/setup-sudoers.sh` now ships **`99-stm32-dfu.rules`** so DFU flashes without `sudo`. (Self-heal on startup needs root the backend doesn't have — the badge tells the user the one command to run instead.) | DFU-without-sudo + a clear setup light |
| ✅ **14 — Configurator / profile parity** | Closed the Kconfig-editor gaps found vs the reference (gap analysis 2026-05-31): **force `LOW_LEVEL_OPTIONS` + `HAVE_LIMITED_CODE_SIZE`** so the optimization menus always show + **download the built binary** (v0.18.0) · **profile rename** (moves config + artifacts + rewrites device refs) · **duplicate / save-as** · **build auto-saves** pending edits first (v0.19.0) · **inline help** toggle · **Profile Info** card · **show-raw-symbol-names** toggle · render Kconfig **comments** · `readonly` on select/input · node `default` / `dep_str` hints (v0.20.0) | a complete firmware configurator |

**Ideas (not yet sequenced)**

- 📋 One-click "Check & Upgrade" (installed vs upstream, per device) · Pre-flight checks · Board profile library (EBB36, Spider, …) · Scheduled flash · Flash audit log · Guided wizard
- 📋 Firmware backup + rollback · App self-update from the UI ("N commits behind" badge) · Kalico firmware-name detection · Test-DFU-Cycle + Katapult native wire-protocol (deferred from Phase 10)
- ✅ MCU telemetry (freq / load / retransmits) — v0.7.0 · Host↔MCU **update/mismatch alert** (per-device ⚠ badge: live MCU firmware vs the host's running Klipper) — v0.17.x

### ✅ Input Shaping

Turn a Klipper resonance capture into a ready-to-paste `[input_shaper]` config —
no command line. Vendors Klipper's own `shaper_calibrate` so the math matches
`SHAPER_CALIBRATE`. **Shipped v0.27.0 → v0.44.0 — a complete resonance-tuning suite.**

| Phase | Scope |
| ----- | ----- |
| ✅ **1 — Analyze** | Upload a resonance `.csv` → recommended shaper + per-shaper table (freq / residual vibration / smoothing / suggested `max_accel`). |
| ✅ **2 — Chart** | Dependency-free SVG frequency-response plot — PSD curves (X/Y/Z/sum) over the per-shaper vibration-reduction curves. |
| ✅ **3 — Config** | Generates the `[input_shaper]` block; an X and a Y capture combine into one block; copy to clipboard. |
| ✅ **4 — Advanced + compare** | Calibration knobs (`max_freq`, `scv`, `max_smoothing`, `damping_ratio`); **A⇄B** comparison of two captures; localStorage history. |
| ✅ **5 — From the printer** | Import the resonance CSVs Klipper wrote on the host (scans `/tmp` + `printer_data/config`), or **run a live `TEST_RESONANCES`** (auto-homes, waits for the background CSV write to settle) and analyze the result. |
| ✅ **6 — Advanced insights** | Measurement **quality grade (A–F)** + 0–100 score with a factor breakdown; **visual diagnostics** with hand-drawn SVG illustrations + fixes (incl. a cross-axis X/Y imbalance card); **annotated chart** (dominant-peak marker + noise floor). |
| ✅ **7 — Noise pre-check** | Motion-free `MEASURE_AXES_NOISE` reads the accelerometer's idle noise floor and grades it (quiet / elevated / too noisy, per Klipper's ~1–100 normal range), validating the sensor mount before a test. |
| ✅ **8 — Belt comparison** | CoreXY belt-tension comparison: a resonance test along each belt diagonal (`(1,1)` / `(1,-1)`), the two responses overlaid with a matched-vs-mismatch verdict from the dominant-peak frequencies. |
| ✅ **9 — Grade-tracked history** | The calibration history records the quality grade (A–F + score) per run and shows a trend (▲/▼) vs. the previous test of the same axis. |
| ✅ **10 — Axes-map calibration** | Jog +X/+Y/+Z, integrate the accelerometer to velocity, and detect the Klipper `axes_map` (orientation) + tilt/confidence; reconstructs the no-signal axis on bed-slingers. First of the advanced resonance set; builds the `ACCELEROMETER_MEASURE` capture spine. |
| ✅ **11 — Sustain frequency** | Hold the toolhead vibrating near a frequency (a slow, narrow `TEST_RESONANCES` sweep — no macro/config change) to find the resonance source by hand; returns a frequency×time spectrogram + an energy "touch timeline". |
| ✅ **12 — Guided tuning wizard** | A step-by-step walk-through (Noise → Belts → Shaper X → Shaper Y) with automated pass/fail gates (reusing the grade / belt verdict / noise grade) + ranked next-step suggestions; the captures feed the shared config + history. |
| ✅ **13 — Vibrations profile** | Sweep many speeds along each motor angle (0/90 Cartesian/CoreXZ, 45/135 CoreXY) → the smoothest speed ranges + the resonance speeds to avoid, a polar energy plot by travel direction, an angle×speed heatmap, motor symmetry and the motors' resonant frequency. Upgrades the wizard's Vibrations step from a self-report to a measured one. (Pure numpy vibrations analysis, reusing the vendored `ShaperCalibrate`.) |

**Advanced resonance suite — ✅ COMPLETE (5 of 5 shipped)**

- ✅ **Axes-map calibration** (phase 10, v0.39.0)
- ✅ **Sustain frequency** (phase 11, v0.40.0)
- ✅ **Guided wizard** (phase 12, v0.41.0) + the **Vibrations + Pressure-Advance** steps (v0.42.0) — full Noise → Belts → Shaper → Vibrations → PA flow
- ✅ **Vibrations profile** (phase 13, backend v0.43.0 + UI/wizard v0.44.0) — speed×angle vibration map → slicer speed guidance; the wizard's Vibrations step is now measured

**Phase 14 — Widget reorganization & UX overhaul ✅ COMPLETE (v0.45.0 → v0.50.0)**

A focused, multi-PR pass that simplified the widget after the feature build-out: clearer navigation, on-host persistence, a unified file source, an aggregated audit, and inline teaching.

- ✅ **Information architecture** (v0.45.0) — the six stacked toggle panels become a four-view tab strip: **Guided** (default) / **Analyze** / **Live tools** / **Audit**; the guided wizard stays mounted so an in-progress run survives a tab switch.
- ✅ **Explanations + illustrations** (v0.46.0) — per-tool "what's this / how to read it" help + new hand-drawn SVGs, collapsed by default.
- ✅ **Per-tool motion confirm** (v0.46.1) — each on-printer tool gets its own "moves the toolhead" gate (live / belts / axes-map split into separate panels).
- ✅ **Persistent host archive** — a dedicated folder keeps recent scans + generated configs (review / download / delete), retention-bounded. Backend v0.47.0 + browser UI v0.48.0.
- ✅ **Unified CSV source** (v0.48.0) — one chooser for an external upload *or* a local/host file (host dirs + archive).
- ✅ **Aggregated Audit** (v0.49.0 + v0.50.0) — every result (shaper / noise / belts / axes-map / sustain / vibrations) organized by property in one view, merged with the archive; folds in the grade history.

Plus a CI guard that fails on a stale committed `frontend/dist`.

**Ideas (not yet sequenced)**

- 📋 Re-test recommendations from the grade · write the chosen `[input_shaper]` straight to `printer.cfg`.

### ✅ Motor Drivers

Understand and tune the TMC stepper drivers on any Klipper printer — from a read-only
dashboard up to a guided tuning wizard. **Core shipped v0.51.0 → v0.59.0 (P1–P8); homing
coverage (P9) v0.61.0.** **Generic by design:** drivers are detected from
the live config (any axis layout), and all TMC models are handled (2209 / 2208 / 2130 /
2240 / 5160 / 2660…) by reading what the running config exposes — never hardcoded to one
board. Reimplements the `motor_constants` physics (like the vendored `shaper_calibrate`)
so recommendations work even without the `klipper_tmc_autotune` host extra installed.

| Phase | Scope | Risk |
| ----- | ----- | ---- |
| ✅ **1 — Dashboard** | Read-only inventory: every `tmcXXXX <stepper>` with run/hold current (live vs configured), chopper mode, microsteps, sense resistor, StallGuard threshold, temperature, a live health badge (`drv_status`), capability chips, and an advanced-register view. Glossary + illustrated help + "how to read this" steps. (`drivers_service` + `GET /api/drivers/status`) | low (read-only) |
| ✅ **2a — Capability map** | Annotate each driver with authoritative per-model reference data (interface UART/SPI, current cap, chopper modes, StallGuard field, sensorless / temperature) from a curated catalog verified against the Klipper/Kalico code; a ⚠ near-cap hint. (`GET /api/drivers/catalog`) | low (read-only) |
| ✅ **2b — Motor picker** | A searchable catalog of 200+ motors; assign the motor on each stepper (its datasheet specs surface on the card), persisted to `<data_dir>/motor-mapping.json`. (`GET /api/drivers/motors`, `GET`/`POST /api/drivers/mapping`) | low |
| ✅ **3 — Recommender** | Pure `motor_constants` port → recommended run current + StealthChop/SpreadCycle registers (pwm_grad/pwm_ofs/hstrt/hend) from datasheet specs + supply voltage; preview diffed vs live. Compute-only. (`POST /api/drivers/recommend`) | low (compute) |
| ✅ **4 — Apply** | Copy-to-config, gated live `SET_TMC_CURRENT` / `SET_TMC_FIELD` writes (explicit confirm + refused while printing + value validation), `INIT_TMC` revert, and drive `AUTOTUNE_TMC` when the extra is installed. (`POST /api/drivers/config-block · /apply · /init · /autotune`) | high (writes registers) |
| ✅ **5 — Sensorless homing** | StallGuard threshold helper (`sgthrs` / `sgt` / `sg4_thrs`) — gated set + gated test-home (`G28 <axis>`) with a crash warning; guidance to dial it in. (`POST /api/drivers/stallguard · /home`) | high (motion) |
| ✅ **6 — Live monitor** | Per-driver live `drv_status` telemetry (~1.5 s poll): temperature, `SG_RESULT` (+ sparkline), `CS_ACTUAL`, fault flags. (`GET /api/drivers/live/{stepper}`) | low (read-only) |
| ✅ **7 — Tuning wizard** | A 🧭 Guided view walking one driver through choose → motor → recommend & apply → sensorless → done, reusing the dashboard panels with a step breadcrumb + Back/Next. | medium |
| ✅ **8 — Motors-sync** | Drive the optional `motors_sync` add-on for multi-motor phase alignment (dual / quad-Z, dual-X) — detect + gated `SYNC_MOTORS` / `SYNC_MOTORS_CALIBRATE`. (`GET`/`POST /api/drivers/motors-sync`) | high (motion) |
| ✅ **9 — Homing coverage** | Classify each axis's homing method from `[stepper_*].endstop_pin` (physical switch / sensorless / Z-probe / virtual / shared) via Klipper's own rule, and render a method-aware **🏠 homing** panel — live switch state + plain test-home for physical, per-model StallGuard polarity (signed `sgt` vs unsigned `sgthrs` / `sg4_thrs`) for sensorless, a probe pointer for Z. The sensorless tuner now appears only where it applies. (`GET /api/drivers/endstops`) | medium (motion) |
| ✅ **10 — Advanced register editing** | Safe, model-aware editing of more TMC registers behind a server-side per-field allowlist + clamp (StallGuard polarity, CoolStep, chopper timing, thresholds), with raw current-scaling and protection-defeat fields blocked. (#102) **P10a (v0.62.0):** the `field_policy` safety foundation — mask-derived clamp + per-model signedness + blocklist + per-model `current_cap` (2240 from `rref`); sensorless write server-clamped; writes refused while printing/paused/error. **P10b (v0.63.0):** the **⚙ tune registers** editor — `POST /api/drivers/field` (gated, server-clamped, velocity→TSTEP) + `GET /api/drivers/field-policy/{model}`, an editable grid driven by the server policy (per-field control + range + confirm), `INIT_TMC` reset, read-only registers beneath. **P10c (v0.64.0):** CoolStep single-toggle (vetted set, `POST /api/drivers/coolstep`), per-model StallGuard polarity hints, `toff`/`tbl` pairing note, illustrated help. | high (writes registers) |

## Internationalization (i18n)

Make the UI multilingual on an **offline-first, extensible** `vue-i18n` foundation — adding a
language is dropping a catalog folder, no component edits. Target locales: **en · ar · de ·
zh-Hans · fr · es · ru** (Arabic is RTL with Western `latn` digits). Externalizing the existing
English copy proceeds phase-by-phase; see
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#internationalization-i18n).

| Phase | Scope | Status |
| ----- | ----- | ------ |
| **0 — Scaffolding** | `vue-i18n` v11 + Vite plugin; `core/i18n.ts` (eager `en`, lazy locales, detection, `localStorage` persistence, reactive `<html lang/dir>`); namespaced `en` catalogs; type-safe keys; `LanguageSelect` (hidden until a 2nd locale ships); CI key-diff + pseudo-localization tooling. No user-visible change. | ✅ v0.74.0 |
| **1 — Shell + Input Shaping** | The app shell + the **entire** Input Shaping widget externalized end-to-end as the reference pattern: shell chrome, the help layer, the prose display helpers (grade / diagnose / compare / recommend / axesMap / guided / audit — calling the global translator so they stay test-stable), the guided wizard, and all widget templates (inline markup via `<i18n-t>`; units / tokens kept literal). | ✅ v0.75.0–v0.79.0 |
| **2 — Remaining widgets** | Motor Drivers + Firmware Manager externalized end-to-end (help layers, display helpers, every panel + orchestrator); tab / action label arrays became `computed`; real counts use vue-i18n pipe plurals; inline markup via `<i18n-t>`; technical build-log output kept English. | ✅ v0.80.0–v0.83.0 |
| **3 — RTL + Arabic** | Arabic catalog (845 keys) + 6-form plural rule + `latn` digits; `<html dir/lang>` flips to RTL; logical-property sweep (`ms-/me-/ps-/pe-/text-start/end`, sidebar/drawer flip); `:lang(ar)` Arabic font stack + brutalist tweaks (drop uppercase/tracking, mirror the button press, keep the offset shadow). _Minor follow-ups:_ bidi-isolated measurements, self-hosted Arabic webfonts. | ✅ v0.84.0–v0.85.0 |
| **4 — Backend messages** | A `{ code, params, message }` contract for backend user-facing strings; the frontend owns the translated copy (English `message` kept as a fallback). Done for the Motor Drivers write path (`drivers_apply.py` → `motorDrivers.apply.*`, rendered via `applyResultText`); passthrough/upstream errors (Moonraker / `field_policy` / validation) intentionally stay English (no `code`). | ✅ v0.86.0 |
| **5 — More locales** | de / zh-Hans / fr / es / ru shipped — all 845 keys each, lazy-loaded, with correct per-locale plural rules. Each was a drop-in `src/locales/<code>/` folder; no component changed. (CJK / Cyrillic font subsets ride the default system stack for now.) | ✅ v0.84.0 |

## Planned expansion — reuse from the Klipper ecosystem

A roadmap of new widgets and enhancements extending FilaMind across the full Klipper tuning +
configuration surface (max volumetric flow, a config editor, a macro simulator, board topology,
a hardware browser). Delivery is phased; **Phase 0 (a shared data + config-engine foundation)
lands first** and unblocks the rest, which then run on two parallel tracks. Every item keeps the
project conventions (i18n ×7, theme-aware, confirm-gates for any motion/write, `gcode`-driven via
Moonraker).

| Phase | Scope | Track | Risk |
| ----- | ----- | ----- | ---- |
| 🚧 **0 — Foundation** | **Reference-data layer ✅ v0.92.0** (per-driver StallGuard knowledge base, hotend melt-zone/flow tables, board/MCU patterns, built-in macro defs — read-only `/api/reference/*`). **Config engine ✅ v0.93.0** (`klipper_config` round-trip parse/dump/validate) + **flow-analysis core ✅ v0.93.0** (`max_flow` StallGuard slip-detection). 📋 Remaining: the hardware DB (lands with the Hardware Browser); a fuller config schema/validator grows with the Config Editor | shared | low |
| ✅ **A1 — Config Editor** | `printer.cfg` editor. **Read path ✅ v0.94.0** (`/api/config/files` + `/api/config/file`). **Viewer UI ✅ v0.95.0** (file picker → collapsible sections → params, validation banner, structured/raw views, illustrated help, i18n ×7). **Gated save ✅ v0.96.0** (edit raw → auto-backup → write → optional `FIRMWARE_RESTART`, behind a confirm; refused while printing). 📋 Optional polish: inline structured editing + a diff view. | A | medium (writes cfg) |
| ✅ **A2 — Macro Designer** | Offline G-code/macro simulator. **Simulator core ✅ v0.101.0** · **Editor UI ✅ v0.102.0** (2D path + bounds/totals/time + timeline + macro library) · **Macro variable substitution ✅ v0.106.0** (`{ params.X | default(N) }` rendered before simulating). 📋 Optional future: full Jinja control-flow (`{% for/if %}`) — needs the jinja2 engine + a printer-runtime-state model. | A | low (no motion) |
| ✅ **A3 — Board Topology** | Auto board/MCU detection + a visual host↔MCU topology. **Detection backend ✅ v0.99.0** (`GET /api/topology`). **Topology UI ✅ v0.100.0** (host → MCU cards with connection type / chip / board guess, i18n ×7). 📋 Optional: a pin-conflict validator (best paired with the Config Editor's unsaved-edit flow). | A | low (read-only) |
| ✅ **A4 — Hardware Browser + Templates** | Searchable unified hardware DB (3,671 components) + an insertable config/macro template library. **Data + search backend ✅ v0.103.0** · **Browser UI ✅ v0.104.0** · **Config Templates library ✅ v0.105.0** (curated config blocks + macros, category-filtered, copy-to-clipboard, i18n ×7). | A | low (read-only) |
| 🚧 **B1 — Max-Flow** | Measure the real max volumetric flow (mm³/s) via TMC StallGuard slip detection, + 80/90 % slicer values. **Analysis core ✅ v0.93.0** · **Planner ✅ v0.97.0** · **Measurement loop + UI ✅ v0.98.0** (`/api/maxflow/run`: heat → ramp → sample SG → analyze; heater always cut, stops at first slip, refused while printing; widget with safety checklist + confirm gate + slicer recommendations, i18n ×7). 📋 Next: a live run on the SV08 to validate the TMC2209 extruder's live StallGuard field (the one open item). | B | high (heat + motion) |
| 📋 **B2 — Motor Drivers “Phase 11”** | Auto-SGT calibration + multi-pattern slip-detection insights + thermal-stress diagnostic on the existing tuner; a Sensorless-Homing wizard (adds the missing TMC2209 **SG4** logic) | B | medium |

## Platform

- 📋 Smart "Back to UI" (auto-detect Mainsail / Fluidd, host-preserving link)
- 📋 Declarative `update_manager` deps (virtualenv / requirements / system_dependencies)
- 📋 Self-hosted fonts for fully offline hosts
