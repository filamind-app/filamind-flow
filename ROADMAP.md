# FilaMind Flow — Roadmap

A living roadmap — updated as features land. Each feature ships on its own branch
→ Pull Request → tagged release.

**Legend:** ✅ done · 🚧 in progress · 📋 planned

## Widgets

### 🚧 Firmware Upgrade

Configure, build, flash and upgrade the firmware on every MCU of your printer —
from the browser, no command line.

| Phase | Scope | Risk |
| ----- | ----- | ---- |
| ✅ **1 — Foundation** | Firmware status: per-MCU versions, host↔MCU sync check, tool readiness, Linux host MCU | low (read-only) |
| ✅ **2 — Discover** | Detect every board on any printer — Moonraker `[mcu]` + USB / CAN / DFU scans, with connection + mode | low (read-only) |
| ✅ **3 — Configure** | Web Kconfig editor (reactive form) + saved per-board profiles | medium |
| ✅ **4 — Build** | Compile firmware for a profile, with live streamed log | medium |
| 🚧 **5 — Flash** | Flash via Katapult / DFU / avrdude, auto-reboot to bootloader, safety guards | high (touches hardware) |

**Planned enhancements**

- 📋 One-click "Check & Upgrade" — compare installed vs upstream, update in one click
- 📋 Host ↔ MCU version-mismatch alerts (a common Klipper failure mode)
- 📋 Pre-flight checks (Katapult/CAN/device reachable) before flashing
- 📋 Firmware backup + rollback where supported
- 📋 Board profile library (EBB36, Spider, …) — import a ready profile
- 📋 Schedule a flash for after the current print finishes
- 📋 Flash audit log (what / when / which version)
- 📋 Guided first-time wizard (detect board → profile → build → flash)
- 📋 MCU telemetry (load, frequency, comms errors) in the device list

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
