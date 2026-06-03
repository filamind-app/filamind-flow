<div align="center">

# FilaMind Flow

**An extensible, Neo-Brutalist control panel for Klipper / Moonraker** — built to live
alongside Mainsail and Fluidd and grow one widget at a time.

[![CI](https://github.com/filamind-app/filamind-flow/actions/workflows/ci.yml/badge.svg)](https://github.com/filamind-app/filamind-flow/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/filamind-app/filamind-flow?color=111111&label=release&sort=semver)](https://github.com/filamind-app/filamind-flow/releases/latest)
[![License: GPLv3](https://img.shields.io/badge/License-GPLv3-111111.svg)](LICENSE)
[![Last commit](https://img.shields.io/github/last-commit/filamind-app/filamind-flow?color=111111&label=updated)](https://github.com/filamind-app/filamind-flow/commits/main)

[![Klipper](https://img.shields.io/badge/Klipper-compatible-111111)](https://www.klipper3d.org)
[![Moonraker](https://img.shields.io/badge/Moonraker-API-111111)](https://moonraker.readthedocs.io)
[![Mainsail](https://img.shields.io/badge/Mainsail-sidebar-111111)](https://docs.mainsail.xyz)
[![Fluidd](https://img.shields.io/badge/Fluidd-ready-111111)](https://docs.fluidd.xyz)

[![Vue.js](https://img.shields.io/badge/Vue.js-3-4FC08D?logo=vuedotjs&logoColor=white)](https://vuejs.org)
[![Vite](https://img.shields.io/badge/Vite-6-646CFF?logo=vite&logoColor=white)](https://vite.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-06B6D4?logo=tailwindcss&logoColor=white)](https://tailwindcss.com)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org)

[Install](#install-on-a-printer-one-line) · [Widgets](#widgets) · [Architecture](#architecture) · [Quickstart](#quickstart) · [Roadmap](ROADMAP.md) · [Contributing](CONTRIBUTING.md)

</div>

FilaMind Flow is a standalone single-page app that talks **directly to Moonraker**
(REST + WebSocket JSON-RPC) and is linked from the Mainsail sidebar (and reached by
URL from Fluidd, which has no custom-link API yet) — the same integration model as
the rest of the ecosystem. The frontend is built once
on your machine and deployed as **static files**, so it adds virtually nothing to
the printer host at runtime; a small FastAPI backend handles anything that must
run server-side.

> **Status:** actively developed and **running on real hardware** (a Sovol SV08).
> Three widgets ship today:
>
> - **Firmware Upgrade** — a full Klipper firmware build & flash console: per-board
>   profiles, a live Kconfig editor, Katapult / DFU / SD-card flashing, Beacon probe
>   updates, host service control, host↔MCU update alerts, and an external-firmware
>   inspector / diff.
> - **Input Shaping** — turn a Klipper resonance capture into a ready
>   `[input_shaper]` config without the command line: the recommended shaper, an SVG
>   frequency-response chart, per-axis X/Y, an A⇄B comparison, a **measurement
>   quality grade (A–F)**, and **visual diagnostics with illustrated fixes**. Import
>   captures from the printer host or run a live test, compare CoreXY belts, detect the
>   accelerometer axes-map, hold a sustain frequency, sweep a **machine vibrations
>   profile** (smoothest speeds + resonances to avoid), and walk it all in a guided wizard.
> - **Motor Drivers** — a live inventory of every TMC stepper driver, read straight from
>   the Klipper config: per-motor run/hold current, chopper mode (SpreadCycle / StealthChop),
>   microsteps, StallGuard threshold, temperature, and a live health badge — with a built-in
>   glossary, illustrated help, and advanced register view. Works on any Klipper printer and
>   any TMC model.
>
> Further widgets are added under `frontend/src/widgets/`.

## Widgets

| Widget | What it does | Status |
| ------ | ------------ | ------ |
| **Firmware Upgrade** | Build & flash Klipper firmware on every MCU — per-board Kconfig profiles, a live web editor, Katapult / DFU / SD-card flashing, Beacon probe updates, host service control, host↔MCU update alerts, and an external-firmware inspector / diff. | ✅ Shipped |
| **Input Shaping** | Turn a resonance capture into a ready `[input_shaper]` config — recommended shaper, SVG frequency-response chart, per-axis X/Y, A⇄B compare, a quality grade (A–F) with illustrated diagnostics, live tests, belt & axes-map & vibration tooling, and a guided wizard. **Full Shake&Tune parity.** | ✅ Shipped |
| **Motor Drivers** | A live inventory of every TMC stepper driver, read straight from the Klipper config — run/hold current, chopper mode, microsteps, StallGuard, temperature, and health, each annotated with authoritative per-model facts from a built-in capability map. Assign each axis its motor from a 200+ motor catalog, then preview recommended run current + driver registers from the motor's datasheet (a faithful `motor_constants` port). Glossary + illustrated help. Generic across all printers and TMC models. | 🚧 P1–P3 (dashboard · capability map · motor picker · recommender) |

See [ROADMAP.md](ROADMAP.md) for the phase-by-phase plan of each widget.

## Install on a printer (one line)

On your Klipper / Moonraker host, run as your normal printer user (e.g. `pi` / `biqu`):

```bash
curl -fsSL https://raw.githubusercontent.com/filamind-app/filamind-flow/main/scripts/install.sh | bash
```

It installs the backend service, serves the (pre-built) UI via nginx on port `8090`,
adds a **FilaMind Flow** entry to the Mainsail sidebar, and registers it with
Moonraker's update manager for one-click updates. Re-runnable; ports are overridable
(`FILAMIND_UI_PORT`, `FILAMIND_API_PORT`), and the sidebar-link host with
`FILAMIND_PUBLIC_HOST` (defaults to the LAN IP — more portable than `<hostname>.local`,
which needs mDNS the client may not have). See [`scripts/install.sh`](scripts/install.sh).

## Why it exists

- **Extensible by construction** — every feature is a self-registering _widget_.
  Adding one is dropping a file; the core never changes.
- **Light on the host** — static frontend + a lean async backend. The browser
  does the work, not the Raspberry Pi.
- **Opinionated design** — a cohesive Neo-Brutalist system (thick ink borders,
  hard offset shadows, high-contrast flat accents) instead of ad-hoc styling.

## Architecture

```
┌────────────────────────────┐        ┌──────────────┐      ┌──────────┐
│  FilaMind Flow (SPA)        │  REST  │              │ Unix │          │
│  Vue 3 · Vite · TS · TW     │◄──────►│  Moonraker   │◄────►│ Klipper  │
│                             │   WS   │   :7125      │ sock │  (MCU)   │
│  ┌──────────────────────┐   │◄──────►│              │      │          │
│  │ MoonrakerClient (WS) │   │        └──────────────┘      └──────────┘
│  │ Widget registry      │   │               ▲
│  │ Pinia printer store  │   │  REST /api    │ shares the same Moonraker
│  └──────────────────────┘   │──────────────►┌──────────────┐
└────────────────────────────┘                │ FastAPI      │
        ▲ linked from sidebar                  │ backend :8000│
   Mainsail · Fluidd                           └──────────────┘
```

- **MoonrakerClient** — one reconnecting JSON-RPC WebSocket; correlates requests,
  fans out `notify_*` notifications, restores subscriptions after a reconnect.
- **Widget registry** — the extensibility core; widgets declare the printer
  objects they need and the dashboard subscribes to their union, once.
- **Pinia store** — a single reactive mirror of Moonraker state for all widgets.
- **FastAPI backend** — health + diagnostics, plus the firmware build/flash and
  resonance-analysis services; the home for privileged or aggregated server-side
  operations.

## Tech stack

| Layer    | Stack                                              |
| -------- | -------------------------------------------------- |
| Frontend | Vue 3, Vite, TypeScript, Tailwind CSS v3, Pinia    |
| Backend  | FastAPI, Uvicorn, httpx, Pydantic v2               |
| Tooling  | ESLint (flat) + Prettier, Vitest · Ruff + Mypy + Pytest |

## Quickstart

### Frontend

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173 (proxies Moonraker + the backend)
```

Point it at a printer by copying `.env.example` to `.env` and setting
`VITE_MOONRAKER_HTTP_URL` / `VITE_MOONRAKER_WS_URL`.

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
python -m app        # http://localhost:8000  (docs at /docs)
```

## Project structure

```
filamind-flow/
├─ frontend/                 # Vue 3 + Vite + TS + Tailwind SPA
│  └─ src/
│     ├─ core/               # MoonrakerClient · widget registry · Pinia store
│     ├─ components/         # App shell + dashboard (design-system driven)
│     ├─ widgets/            # Feature widgets register here (Firmware Upgrade + Input Shaping + Motor Drivers ship today)
│     └─ assets/styles/      # Neo-Brutalist design tokens
├─ backend/                  # FastAPI service
│  └─ app/                   # config · api/routes · services · models
├─ deploy/                   # systemd · nginx · Moonraker update_manager · navi.json
├─ docs/ARCHITECTURE.md      # design + data-flow deep dive
└─ .github/workflows/ci.yml  # lint · type-check · test · build
```

## Adding a widget

```ts
// frontend/src/widgets/index.ts
import { defineAsyncComponent } from 'vue'
import { registerWidget } from '@/core/registry'

export function registerWidgets(): void {
  registerWidget({
    id: 'temperature',
    title: 'Temperatures',
    defaultSize: { w: 2, h: 1 },
    subscriptions: { extruder: null, heater_bed: null }, // printer objects to watch
    component: defineAsyncComponent(() => import('./temperature/TemperatureWidget.vue')),
  })
}
```

Inside the widget, read live data from the shared store:

```ts
import { usePrinterStore } from '@/core/store/printer'
const printer = usePrinterStore()
// printer.status.extruder?.temperature, etc.
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full guide and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
for the design rationale.

## Documentation

| Document | What's inside |
| -------- | ------------- |
| [ROADMAP.md](ROADMAP.md) | Phase-by-phase plan and status for every widget |
| [CHANGELOG.md](CHANGELOG.md) | Release history (Keep a Changelog) |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Dev workflow, conventions, widget-UX rule, release process |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Design + data-flow deep dive |
| [backend/README.md](backend/README.md) | Backend service, `/api` endpoints, `FILAMIND_*` settings |

## Deployment

Build the frontend (`npm run build` → `frontend/dist/`), serve it with nginx, run
the backend as a systemd service, and add a sidebar link in Mainsail. Ready-to-edit
templates live in [`deploy/`](deploy/).

## Roadmap

- [x] **Firmware Upgrade** widget — build & flash Klipper firmware: per-board
      profiles, a live Kconfig editor (with downloadable build artifacts),
      Katapult / DFU / SD-card flashing, Beacon probe updates, host service
      control, and host↔MCU update alerts
- [x] **Input Shaping** widget — resonance capture → `[input_shaper]` config:
      recommended shaper, SVG frequency-response chart, per-axis X/Y, A⇄B compare,
      a measurement **quality grade (A–F)**, **visual diagnostics with fixes**,
      printer-host import, a live test, an accelerometer noise pre-check, a
      CoreXY belt-tension comparison, accelerometer axes-map detection, a
      sustain-frequency hands-on diagnostic, a machine **vibrations profile**
      (smoothest/worst speeds, motor symmetry, motor resonance), and a guided
      tuning wizard
- [x] **Motor Drivers** widget (P1) — live TMC driver dashboard: per-motor run/hold
      current, chopper mode, microsteps, StallGuard, temperature + health, with a
      glossary and illustrated help; generic across all Klipper printers and TMC models
- [ ] Self-hosted fonts for fully offline hosts
- [ ] Optional auth/oneshot-token flow for secured Moonraker setups

See [ROADMAP.md](ROADMAP.md) for the full phase-by-phase plan.

## Credits

Built and maintained by the **DeltaFabs team**:

- abdelmonem awad — <eg2@live.com>
- Ahmed bebars — <Ahmedbebars1@gmail.com>

## License

[GPL-3.0-or-later](LICENSE) © 2026 DeltaFabs team. Not affiliated with the Klipper,
Moonraker, Mainsail, or Fluidd projects.
