# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
  sidebar** (alongside KlipperFleet), with klippy `ready` and a live Connected badge.

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

[Unreleased]: https://github.com/filamind-app/filamind-flow/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.3.0
[0.2.2]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.2.2
[0.2.1]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.2.1
[0.2.0]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.2.0
[0.1.0]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.1.0
