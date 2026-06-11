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

> **Status:** actively developed and **running on real hardware** (a Sovol SV08), localized in
> **7 languages** with **4 switchable themes**. **Nine widgets ship today** — Firmware Manager,
> Input Shaping, Motor Drivers, Config Editor, Macro Designer, Board Topology, Max-Flow,
> Config Templates, and the Hardware Browser. A few highlights:
>
> - **Firmware Manager** — a full Klipper firmware build & flash console: per-board
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
>   microsteps, StallGuard threshold, temperature, and a live health badge; datasheet-based
>   tuning recommendations, and a homing panel that adapts to each axis (physical switch /
>   sensorless / Z-probe) — with a built-in glossary, illustrated help, and advanced register
>   view. Works on any Klipper printer and any TMC model.
> - **Hardware Browser** — a curated database of thousands of 3D-printing components
>   (boards · drivers · motors · hosts · sensors · hotends · extruders · nozzles · fans ·
>   filament · …), deduped into **2,600+ canonical entities each with a copyable Klipper
>   config**: board pin-maps, `[tmcXXXX]` driver blocks, recommended motor `run_current`,
>   `[mcu host]` host blocks, and more — designed to become the shared data layer every other
>   widget links to.
>
> The full set is in the table below; new widgets are added under `frontend/src/widgets/`.

## Widgets

| Widget | What it does | Status |
| ------ | ------------ | ------ |
| **Firmware Manager** | Build & flash Klipper firmware on every MCU, organized into tabs (Guided / Status / Configure / Devices / External) with a guided new-board walkthrough — per-board Kconfig profiles, a live web editor, Katapult / DFU / SD-card flashing (each behind a flash-plan preview + confirm gate), Beacon probe updates, host service control, host↔MCU update alerts, and an external-firmware inspector / diff. Glossary + illustrated help + a build→flash guide. | ✅ Shipped |
| **Input Shaping** | Turn a resonance capture into a ready `[input_shaper]` config — recommended shaper, SVG frequency-response chart, per-axis X/Y, A⇄B compare, a quality grade (A–F) with illustrated diagnostics, live tests, belt & axes-map & vibration tooling, and a guided wizard. **A complete resonance-tuning suite.** | ✅ Shipped |
| **Config Editor** | Browse your printer's live configuration straight from Moonraker — every `.cfg` / `.conf` file, parsed into `[sections]` → parameters (value + inline comment, multi-line values intact) with the `SAVE_CONFIG` block flagged and structural problems (e.g. a duplicate section) surfaced in a validation banner. Structured and raw views, file picker, illustrated help. **Edit the raw config and save it back behind a confirm gate** — an automatic timestamped backup is taken first, writes are refused while printing, and a one-click `FIRMWARE_RESTART` applies the change. **Insert a hardware-accurate config block from the catalog** — pick a driver / motor / board and its real `[tmcXXXX]` / pin-map block (correct `run_current`, `sense_resistor`, pin names) is appended for review. **Disk-vs-live drift healer** — see which values you edited but never restarted (and any pending `SAVE_CONFIG`), with one-click "adopt live" per param. **Pin Doctor** — a whole-config scan that flags double-assigned pins and mains-on-logic-pin caveats before you `FIRMWARE_RESTART`. **Structured-view inline editing** — `[tmcXXXX]` register fields render with the right control and silicon-fact range (number clamped to the register mask, enum dropdown, boolean checkbox), and every `*_pin` field offers its board's named pins as type-ahead suggestions with inline flags for an off-board / reused / electronics-caveat pin; edits ride the surgical round-trip writer and the gated save. **Project view** — an `[include]` dependency tree across every file, project-wide search that jumps you to the hit, and cross-file lint (broken include, an orphan TMC driver with no matching stepper, plus override visibility for sections redefined across includes). **Inline knowledge** — each expanded section carries a plain-language blurb of what it does, and a driver section deep-links to its catalog entity in the Hardware Browser. **Backup timeline** — browse the automatic pre-save snapshots, diff any one against your current draft, and restore it for a final review behind the same save gate. Generic across all Klipper printers. | ✅ Shipped |
| **Max-Flow** | Measure the highest volumetric flow (mm³/s) your hotend can sustain — ramp the extrusion flow while watching the extruder's TMC StallGuard load for the moment the gear slips. Pick a hotend to prefill, preview the exact ramp (flow → feedrate per step), then run behind a safety checklist + confirm gate; the heater is always cut at the end, the ramp stops at the first slip, and the run is refused while printing. Reports the max sustained flow + suggested slicer "max volumetric speed" (80 % / 90 %). Illustrated help. | ✅ Shipped (planner + gated run) |
| **Board Topology** | An interactive **"Machine Map"** of your printer's control boards — a live SVG node-graph with a **Physical** view (an integrated SBC drawn *inside* the mainboard it ships on, CAN toolheads on a shared backbone, USB / UART boards as separate units) and a **Logical** view (Klipper's host→MCU command tree), edges colour-coded by bus. Click any board, SBC or MCU to inspect its **catalog record** (specs, ports, electronics caveats, config notes, copyable Klipper snippet) and **deep-link into the hardware database**. You can **confirm or override the detected board** per MCU — saved on the host and reused on every read. Illustrated help. Generic across all Klipper printers. | ✅ Shipped |
| **Macro Designer** | An offline G-code simulator: write or paste a program and see the toolhead path drawn in 2D, the bounding box, total travel and extrusion, a time estimate, and a per-command timeline — nothing is sent to the printer. An **"Explain this macro"** walkthrough narrates each command in plain language with the running mode + cumulative totals, hover-synced with the path. **Import and simulate your printer's OWN installed macros** — pick a `[gcode_macro]` and its real body loads + dry-runs, with its parameters discovered into editable fields. The preview is **grounded in your printer's real build area + speed cap** — moves that leave the bed or exceed `max_velocity` are drawn in red and flagged before you run them. A **static linter** catches macro-logic foot-guns (unbalanced `SAVE`/`RESTORE_GCODE_STATE`, ends-in-relative-mode, extrude-before-home). The time estimate is **accel-aware** (a trapezoidal profile from the printer's real `max_accel`/`max_velocity`), and the path can be recoloured as a **speed or extrusion-rate heatmap**. Plus a built-in macro reference library you can insert from. Illustrated help. | ✅ Shipped (simulator + UI) |
| **Hardware Browser** | A curated reference of 3D-printing hardware deduped into **2,600+ canonical entities**, each with its full spec sheet **and a copyable Klipper config**: **Boards** (380 — aggregated pin-map / ports + a copy-ready pin config), **Drivers** (55 — `[tmcXXXX]` blocks for the TMC family, honest notes for standalone parts), **Motors** (670+ — recommended `run_current` + config, incl. real OEM part ranges), **Hosts** (220 SBC / x86 — `[mcu host]`), and a generic **catalog** of 9 more categories (sensors & probes, hotends, extruders, fans / power / bed, cameras & displays, motion, nozzles, filament, electronics), plus browsable **Brands** and **MCUs**. Everything is cross-linked: open a board and jump to its manufacturer, MCU or drivers via clickable chips. Search by name / manufacturer / spec; the shared data layer other widgets link to. Illustrated help. | ✅ Shipped |
| **Config Templates** | A library of ready-to-paste Klipper config blocks and macros — start/end sequences, pause/resume, filament load/unload, M600, `[input_shaper]`, `[bed_mesh]`, `[firmware_retraction]` and more — filterable by category, each with a one-click copy. Illustrated help. | ✅ Shipped |
| **Motor Drivers** | A live inventory of every TMC stepper driver, read straight from the Klipper config — run/hold current, chopper mode, microsteps, StallGuard, temperature, and health, each annotated with authoritative per-model facts from a built-in capability map. Assign each axis its motor from a 200+ motor catalog, get recommended run current + driver registers from the motor's datasheet (a built-in `motor_constants` physics model), and copy-to-config or apply them live behind a confirm (reversible; refused while printing). A method-aware **🏠 homing** panel adapts to how each axis homes (physical switch / sensorless / Z-probe) — live switch state + test-home for switches, a per-model-correct StallGuard tuner for sensorless. An **⚙ advanced register editor** edits the safe subset of TMC registers live behind a server-side allowlist + clamp (raw current and protection registers blocked). Watch a live monitor (temperature / StallGuard load / faults), sync multi-motor axes, or run it all from a **🧭 Guided wizard**. Glossary + illustrated help. Generic across all printers and TMC models. | ✅ Shipped (P1–P10) |

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
- **FastAPI backend** — health + diagnostics, the firmware build/flash and
  resonance-analysis services, the config / topology / max-flow services, and the
  read-only **hardware database** (`/api/hardware/*` — canonical boards / drivers /
  motors / hosts / catalog, each with a copyable Klipper config); the home for
  privileged or aggregated server-side operations.

## Tech stack

| Layer    | Stack                                              |
| -------- | -------------------------------------------------- |
| Frontend | Vue 3, Vite, TypeScript, Tailwind CSS v3, Pinia, vue-i18n |
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
│     ├─ core/               # MoonrakerClient · widget registry · Pinia store · i18n
│     ├─ components/         # App shell + dashboard (design-system driven)
│     ├─ widgets/            # Feature widgets register here (Firmware Manager + Input Shaping + Motor Drivers ship today)
│     ├─ locales/            # Per-language message catalogs (en bundled; others lazy)
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

## Internationalization

The UI is being made multilingual on an **offline-first, extensible** foundation (`vue-i18n` v11).
English is bundled eagerly; every other locale is a lazy chunk under `src/locales/<code>/` — so
**adding a language is dropping in a folder**, no component edits. `en` is the source of truth for
keys (type-checked, so a typo fails the build), and CI enforces that every locale carries exactly
the same key set (`npm run i18n:keydiff`); `npm run i18n:pseudo` previews text-expansion / RTL
overflow. Arabic is wired for RTL with Western (`latn`) digits — engineers cross-reference G-code
and datasheets in `1.7 A` form. Backend write-results follow a `{ code, params, message }` contract:
the API returns a stable code the UI translates (`applyResultText`), keeping the English `message` as
a fallback; raw upstream / validation errors (Moonraker, `field_policy`) intentionally stay English.

> **Status:** Shipped — the UI is available in **7 languages** (**en · ar · de · zh-Hans · fr · es ·
> ru**) via a header switcher; switching is instant and lazy-loaded. Arabic flips the document to RTL
> (with a Neo-Brutalist RTL layout pass). All six i18n phases — scaffolding → widgets → RTL → backend
> message codes — are complete.

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

- [x] **Firmware Manager** widget — build & flash Klipper firmware: per-board
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
- [x] **Motor Drivers** widget (P1–P10) — live TMC driver dashboard + capability map,
      a 200+ motor picker, datasheet-based tuning recommendations (a built-in
      `motor_constants` physics model), gated apply / copy-to-config / autotune, a method-aware
      homing panel (physical switch / sensorless with per-model StallGuard polarity / Z-probe),
      an advanced register editor (server-side allowlist + clamp; raw current/protection blocked),
      a live monitor, a guided wizard, and multi-motor synchronization; generic across
      all Klipper printers and TMC models
- [x] **Internationalization (i18n)** — multilingual UI on an offline-first, extensible
      `vue-i18n` foundation (en · ar · de · zh-Hans · fr · es · ru), RTL + Arabic, and a
      `{ code, params, message }` backend-message contract. _All six phases complete._
- [x] **Theme system** — 4 switchable themes (Neon · Dark · Light · High-Contrast) driven by
      CSS variables; per-theme recolor of every token with no component edits; no-flash + persisted.
- [x] **Platform expansion** — the shared data + config-engine foundation plus **Config Editor**,
      **Macro Designer**, **Board Topology**, **Hardware Browser + Config Templates**, and
      **Max-Flow** (planner + gated run) all shipped. _See [ROADMAP.md](ROADMAP.md)._
- [x] **Hardware database** — the catalog deduped into canonical, config-carrying entities
      (boards / drivers / motors / hosts / catalog) served under `/api/hardware/*`, with O(1)
      id lookups + cached reads (**DB-1**), and a canonical-manufacturer / first-class-MCU
      **linking graph** (`/related` + `?expand=related`, **DB-2**).
- [x] **Hardware DB — cross-link UI (DB-3a)** — clickable cross-link chips (board → its
      manufacturer / MCU / drivers) + browsable **Brands** and **MCUs** tabs + in-widget
      deep-linking.
- [ ] **Hardware DB backbone — remaining** — shared `EntityCatalog` + faceted filters + a
      reusable part-picker (DB-3b), images / silo convergence (DB-4). _See [ROADMAP.md](ROADMAP.md)._
- [ ] Max-Flow: a live validation run on the printer · Motor-Drivers auto-SGT / SG4 sensorless wizard
- [ ] Self-hosted fonts for fully offline hosts · optional auth / oneshot-token flow for secured setups

See [ROADMAP.md](ROADMAP.md) for the full phase-by-phase plan.

## Credits

Built and maintained by the **DeltaFabs team**:

- abdelmonem awad — <eg2@live.com>
- Ahmed bebars — <Ahmedbebars1@gmail.com>

## License

[GPL-3.0-or-later](LICENSE) © 2026 DeltaFabs team. Not affiliated with the Klipper,
Moonraker, Mainsail, or Fluidd projects.
