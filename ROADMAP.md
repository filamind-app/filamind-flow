# FilaMind Flow — Roadmap

A living roadmap — updated as features land. Each feature ships on its own branch
→ Pull Request → tagged release.

**Legend:** ✅ done · 🚧 in progress · 📋 planned

## Widgets

### ✅ Firmware Upgrade

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
`SHAPER_CALIBRATE`. **Shipped v0.27.0 → v0.44.0 — full Shake&Tune feature parity.**

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
| ✅ **10 — Axes-map calibration** | Jog +X/+Y/+Z, integrate the accelerometer to velocity, and detect the Klipper `axes_map` (orientation) + tilt/confidence; reconstructs the no-signal axis on bed-slingers. First of the Shake&Tune-parity set; builds the `ACCELEROMETER_MEASURE` capture spine. |
| ✅ **11 — Sustain frequency** | Hold the toolhead vibrating near a frequency (a slow, narrow `TEST_RESONANCES` sweep — no macro/config change) to find the resonance source by hand; returns a frequency×time spectrogram + an energy "touch timeline". |
| ✅ **12 — Guided tuning wizard** | A step-by-step walk-through (Noise → Belts → Shaper X → Shaper Y) with automated pass/fail gates (reusing the grade / belt verdict / noise grade) + ranked next-step suggestions; the captures feed the shared config + history. |
| ✅ **13 — Vibrations profile** | Sweep many speeds along each motor angle (0/90 Cartesian/CoreXZ, 45/135 CoreXY) → the smoothest speed ranges + the resonance speeds to avoid, a polar energy plot by travel direction, an angle×speed heatmap, motor symmetry and the motors' resonant frequency. Upgrades the wizard's Vibrations step from a self-report to a measured one. (numpy port of Shake&Tune's `vibrations_computation.py`, reusing the vendored `ShaperCalibrate`.) |

**Shake&Tune parity — ✅ COMPLETE (5 of 5 shipped)**

- ✅ **Axes-map calibration** (phase 10, v0.39.0)
- ✅ **Sustain frequency** (phase 11, v0.40.0)
- ✅ **Guided wizard** (phase 12, v0.41.0) + the **Vibrations + Pressure-Advance** steps (v0.42.0) — full Noise → Belts → Shaper → Vibrations → PA flow
- ✅ **Vibrations profile** (phase 13, backend v0.43.0 + UI/wizard v0.44.0) — speed×angle vibration map → slicer speed guidance; the wizard's Vibrations step is now measured

**Phase 14 — Widget reorganization & UX overhaul (in progress)**

A focused, multi-PR pass to simplify the widget after the feature build-out: clearer navigation, on-host persistence, a unified file source, an aggregated audit, and inline teaching.

- ✅ **Information architecture** (v0.45.0) — the six stacked toggle panels become a four-view tab strip: **Guided** (default) / **Analyze** / **Live tools** / **History**; the guided wizard stays mounted so an in-progress run survives a tab switch.
- ✅ **Explanations + illustrations** (v0.46.0) — per-tool "what's this / how to read it" help + new hand-drawn SVGs, collapsed by default.
- ✅ **Per-tool motion confirm** (v0.46.1) — each on-printer tool gets its own "moves the toolhead" gate (live / belts / axes-map split into separate panels).
- ✅ **Persistent host archive** — a dedicated folder keeps recent scans + generated configs (review / download / delete), retention-bounded. Backend v0.47.0 + browser UI v0.48.0.
- ✅ **Unified CSV source** (v0.48.0) — one chooser for an external upload *or* a local/host file (host dirs + archive).
- ⏳ **Aggregated Audit** — every result organized by property; folds in the grade history. Shaper + archive merged into the Audit view v0.49.0; the live tools (noise / belts / axes-map / sustain / vibrations) join next.

**Ideas (not yet sequenced)**

- 📋 Re-test recommendations from the grade · write the chosen `[input_shaper]` straight to `printer.cfg`.

## Platform

- 📋 Smart "Back to UI" (auto-detect Mainsail / Fluidd, host-preserving link)
- 📋 Declarative `update_manager` deps (virtualenv / requirements / system_dependencies)
- 📋 Self-hosted fonts for fully offline hosts
