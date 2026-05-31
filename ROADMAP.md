# FilaMind Flow — Roadmap

A living roadmap — updated as features land. Each feature ships on its own branch
→ Pull Request → tagged release.

**Legend:** ✅ done · 🚧 in progress · 📋 planned

## Widgets

### ✅ Firmware Upgrade

Configure, build, flash and upgrade the firmware on every MCU of your printer —
from the browser, no command line. **The core pipeline (phases 1–5) is complete.**
Phases 6+ close the gaps found against the installed KlipperFleet v1.3.1-alpha.

| Phase | Scope | Risk |
| ----- | ----- | ---- |
| ✅ **1 — Foundation** | Firmware status: per-MCU versions, host↔MCU sync check, tool readiness, Linux host MCU | low (read-only) |
| ✅ **2 — Discover** | Detect every board on any printer — Moonraker `[mcu]` + USB / CAN / DFU scans, with connection + mode | low (read-only) |
| ✅ **3 — Configure** | Web Kconfig editor (reactive form) + saved per-board profiles | medium |
| ✅ **4 — Build** | Compile firmware for a profile, with live streamed log | medium |
| ✅ **5 — Flash** | Flash via Katapult / DFU / `make flash`, reboot-to-bootloader, safety guards (print-lock, sudo, confirm) | high (touches hardware) |

**Next phases — KlipperFleet parity & beyond** (from the gap analysis vs the installed KlipperFleet v1.3.1-alpha)

| Phase | Scope | Closes / unlocks |
| ----- | ----- | ---------------- |
| ✅ **6 — Version tracking** | Capture Klipper version/commit/date at build time (`<profile>.build_info.json` + `get_klipper_version`); show the **built / flashed version** on every board — including the Linux host MCU, which Moonraker can't report | the reported "host MCU shows no version" gap |
| 📋 **7 — Fleet (persistence)** | A saved fleet (`fleet.json`): board↔profile mapping, flashed_version, last_flashed, and per-device settings (baudrate, Katapult serial identity, custom make command, exclude-from-batch, notes) | a persistent dashboard + everything below |
| 📋 **8 — Batch operations** | Build All / Flash All / Flash Ready across the fleet, with service stop/start orchestration | one-click fleet upgrade |
| 📋 **9 — Live status & services** | Live per-device status (service / ready / offline) + start/stop/restart Klipper services from the UI + profile Backup & Restore | |
| 📋 **10 — Advanced flash** | 1200bps magic-baud reboot, DFU retry + `:leave`, USB-to-CAN bridge handling, AVR auto-detect | reliability on more boards |
| 📋 **11 — Beacon** | Beacon eddy-probe firmware (flash + remote-version compare) | Beacon users |

**Ideas (not yet sequenced)**

- 📋 One-click "Check & Upgrade" (installed vs upstream) · Host↔MCU mismatch alerts · Pre-flight checks
- 📋 Firmware backup + rollback · Board profile library (EBB36, Spider, …) · Scheduled flash · Flash audit log · Guided wizard
- 📋 Configurator polish: modified-options count, raw-symbol-names toggle, profile rename
- ✅ MCU telemetry (freq / load / retransmits) — shipped in v0.7.0

### 📋 Other widgets

- 📋 **Temperatures** — live extruder / bed / chamber with targets
- 📋 **Print status & controls** — progress, pause / resume / cancel
- 📋 **Motion** — home / move / disable steppers
- 📋 **Console** — G-code send + streamed response log
- 📋 **Layout persistence** — remember the dashboard layout via Moonraker's database

## Platform

- 📋 Smart "Back to UI" (auto-detect Mainsail / Fluidd, host-preserving link)
- 📋 Declarative `update_manager` deps (virtualenv / requirements / system_dependencies)
- 📋 Self-hosted fonts for fully offline hosts
