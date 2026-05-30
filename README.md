# FilaMind Flow

> An extensible, Neo-Brutalist control panel for **Klipper / Moonraker** — designed
> to live alongside Mainsail and Fluidd and grow one widget at a time.

[![CI](https://github.com/filamind-app/filamind-flow/actions/workflows/ci.yml/badge.svg)](https://github.com/filamind-app/filamind-flow/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-111111.svg)](LICENSE)

FilaMind Flow is a standalone single-page app that talks **directly to Moonraker**
(REST + WebSocket JSON-RPC) and is linked from the Mainsail sidebar (and reached by
URL from Fluidd, which has no custom-link API yet) — the same integration model as
the rest of the ecosystem. The frontend is built once
on your machine and deployed as **static files**, so it adds virtually nothing to
the printer host at runtime; a small FastAPI backend handles anything that must
run server-side.

> **Status:** this is the **empty scaffold** — the architecture, Moonraker client,
> widget registry, design system, and CI are wired and ready. No feature widgets
> ship yet; they are added under `frontend/src/widgets/`.

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
│     ├─ widgets/            # Feature widgets register here (empty scaffold)
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

- [ ] First widgets: temperatures, print status, controls, console
- [ ] Dashboard layout persistence (via Moonraker's database namespace)
- [ ] Self-hosted fonts for fully offline hosts
- [ ] Optional auth/oneshot-token flow for secured Moonraker setups

## Credits

Built and maintained by the **DeltaFabs team**:

- abdelmonem awad — <eg2@live.com>
- Ahmed bebars — <Ahmedbebars1@gmail.com>

## License

[MIT](LICENSE) © 2026 DeltaFabs team. Not affiliated with the Klipper, Moonraker,
Mainsail, or Fluidd projects.
