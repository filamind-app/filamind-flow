# FilaMind Flow

> An extensible, Neo-Brutalist control panel for **Klipper / Moonraker** — designed
> to live alongside Mainsail and Fluidd and grow one widget at a time.

[![CI](https://github.com/filamind-app/filamind-flow/actions/workflows/ci.yml/badge.svg)](https://github.com/filamind-app/filamind-flow/actions/workflows/ci.yml)
[![License: GPLv3](https://img.shields.io/badge/License-GPLv3-111111.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.23.0-111111.svg)](CHANGELOG.md)
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

FilaMind Flow is a standalone single-page app that talks **directly to Moonraker**
(REST + WebSocket JSON-RPC) and is linked from the Mainsail sidebar (and reached by
URL from Fluidd, which has no custom-link API yet) — the same integration model as
the rest of the ecosystem. The frontend is built once
on your machine and deployed as **static files**, so it adds virtually nothing to
the printer host at runtime; a small FastAPI backend handles anything that must
run server-side.

> **Status:** actively developed and **running on real hardware**. The first
> widget — **Firmware Upgrade** — ships today: a full Klipper firmware
> build & flash console (per-board profiles, a live Kconfig editor,
> Katapult / DFU / SD-card flashing, Beacon probe updates, host service control,
> and host↔MCU update alerts). Further widgets are added under
> `frontend/src/widgets/`.

## Install on a printer (one line)

On your Klipper / Moonraker host, run as your normal printer user (e.g. `pi` / `biqu`):

```bash
curl -fsSL https://raw.githubusercontent.com/filamind-app/filamind-flow/main/scripts/install.sh | bash
```

It installs the backend service, serves the (pre-built) UI via nginx on port `8090`,
adds a **FilaMind Flow** entry to the Mainsail sidebar, and registers it with
Moonraker's update manager for one-click updates. Re-runnable; ports are overridable
(`FILAMIND_UI_PORT`, `FILAMIND_API_PORT`). See [`scripts/install.sh`](scripts/install.sh).

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
- **FastAPI backend** — health + diagnostics today; the home for privileged or
  aggregated server-side operations later.

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
│     ├─ widgets/            # Feature widgets register here (Firmware Upgrade ships today)
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

## Deployment

Build the frontend (`npm run build` → `frontend/dist/`), serve it with nginx, run
the backend as a systemd service, and add a sidebar link in Mainsail. Ready-to-edit
templates live in [`deploy/`](deploy/).

## Roadmap

- [x] **Firmware Upgrade** widget — build & flash Klipper firmware: per-board
      profiles, a live Kconfig editor (with downloadable build artifacts),
      Katapult / DFU / SD-card flashing, Beacon probe updates, host service
      control, and host↔MCU update alerts
- [ ] More widgets: temperatures, print status, controls, console
- [ ] Dashboard layout persistence (via Moonraker's database namespace)
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
