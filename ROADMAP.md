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
| 📋 **7 — Fleet (persistence)** | A saved fleet (`fleet.json`): board↔profile mapping, flashed_version, last_flashed, per-device settings (baudrate, custom make command, exclude-from-batch, notes), and a **dual identity per device** (runtime + its separate Katapult-serial / DFU bootloader id); **Add / Attach / Remove** discovered hardware (Attach binds a found bootloader device to an existing fleet entry) | a persistent dashboard + everything below |
| 📋 **8 — Batch operations** | Build All / Flash All / Flash Ready across the fleet, with service stop/start orchestration; **cancel a running build/flash** (task store) + colorized / expandable log panel | one-click fleet upgrade |
| 📋 **9 — Live status, services & reboot** | Live per-device status (service / ready / offline / dfu) with **auto-refresh polling**; **reboot controls** per board (Restart-to-Firmware / Reboot-to-Katapult / Reboot-to-DFU); start/stop/restart Klipper services; **version coloring** (match / mismatch / update-available) | interactive dashboard |
| 📋 **10 — Advanced flash** | 1200bps magic-baud reboot **+ "Test DFU Cycle" validation** (gates auto-DFU / auto-exit), DFU retry + `:leave` + auto-exit, USB-to-CAN bridge handling, AVR auto-detect, **post-flash re-enumeration tracking** (board id changes after flash → auto-update fleet), **Katapult native wire-protocol** return-to-firmware + CAN interface bring-up | reliability on more boards |
| 📋 **11 — Beacon** | Beacon eddy-probe firmware (flash + remote-version compare) | Beacon users |
| 📋 **12 — Backup & Restore** | Export / import a ZIP of the **fleet registry + all Kconfig profiles** (binaries excluded, rebuildable) | migrate or recover a whole setup |
| 📋 **13 — Health & install integrity** | `/api/health` checks (sudoers, **udev DFU rules**, system deps, venv, moonraker.conf) + a UI health indicator; ship a **`99-stm32-dfu.rules`** so DFU flashes without `sudo`; **self-heal** sudoers / system-deps on startup | DFU-without-sudo + zero-touch install |

**Ideas (not yet sequenced)**

- 📋 One-click "Check & Upgrade" (installed vs upstream, per device) · Host↔MCU mismatch alerts · Pre-flight checks
- 📋 Firmware backup + rollback · Board profile library (EBB36, Spider, …) · Scheduled flash · Flash audit log · Guided wizard
- 📋 Configurator polish: modified-options count, raw-symbol-names toggle, profile **rename + duplicate**, Kalico firmware-name detection
- 📋 Download a built binary to the browser · App self-update from the UI ("N commits behind" badge)
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
