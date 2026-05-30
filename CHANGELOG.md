# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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

[Unreleased]: https://github.com/filamind-app/filamind-flow/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.1.0
