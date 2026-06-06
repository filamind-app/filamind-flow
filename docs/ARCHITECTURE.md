# Architecture

This document explains how FilaMind Flow is put together and why. For a quick
start see the root [README](../README.md).

## Goals

1. **Integrate** with Klipper, Moonraker, Mainsail, and Fluidd without forking any
   of them.
2. **Stay light** on the printer host.
3. **Grow** through small, independent features.

## Integration model

The panel is a standalone SPA that talks **directly to Moonraker** and is linked
from the Mainsail sidebar (Fluidd has no custom-link API yet, so it is reached by
URL there). This is the same pattern other ecosystem tools use: there is no stable
third-party plugin API inside Mainsail/Fluidd, so a sibling page sharing the same
Moonraker instance is the clean, durable approach.

```
Browser (phone / desktop)
  └─ FilaMind Flow SPA ──REST──► Moonraker :7125 ──► Klipper (MCU)
                       └──WS───► Moonraker :7125
  └─ FilaMind Flow SPA ──REST──► FilaMind backend :8000 ──► Moonraker (server-side)
```

## Resource footprint

- **Frontend** is built on a developer machine and deployed as static files
  served by nginx (the same web server that already serves Mainsail/Fluidd). At
  runtime the printer host only serves a few static assets; the browser on the
  client device executes the app. Cost on the Pi ≈ that of serving static files.
- **Backend** is a single async Uvicorn process: idle ≈ 30–60 MB RAM and ~0% CPU,
  comparable to Moonraker's own footprint. It is event-driven — no polling loops.
- **WebSocket** subscriptions are limited to the union of the printer objects the
  active widgets actually need, keeping notification traffic minimal.

## Frontend layers

```
src/
├─ core/
│  ├─ moonraker/   # transport: reconnecting JSON-RPC WS client + types + config
│  ├─ registry/    # extensibility: the widget registry
│  ├─ store/       # state: Pinia mirror of Moonraker status
│  └─ i18n.ts      # i18n: catalog loading, locale detection, switching
├─ components/     # presentation: app shell + dashboard (design-system driven)
├─ widgets/        # features: self-registering widgets (Firmware Upgrade · Input Shaping · Motor Drivers)
├─ locales/        # i18n message catalogs, one folder per language (en bundled; others lazy)
└─ assets/styles/  # Neo-Brutalist design tokens + component classes
```

Dependencies point inward: `widgets` and `components` depend on `core`; `core`
depends on nothing app-specific. This keeps the transport and registry reusable
and testable in isolation.

### MoonrakerClient

A single long-lived client (`core/moonraker/client.ts`) owns the WebSocket:

- **Request/response** — each `call()` gets an incrementing id; responses resolve
  the matching pending promise, with a timeout safety net.
- **Notifications** — `notify_*` messages are fanned out to listeners registered
  by method name (e.g. the store listens for `notify_status_update`).
- **Reconnection** — exponential backoff; on reconnect the remembered subscription
  set is re-sent so widgets keep receiving updates transparently.

### Widget lifecycle

1. At startup, `registerWidgets()` calls `registerWidget(...)` for each feature.
2. On connect, the store subscribes to `widgetRegistry.aggregateSubscriptions()`
   — the merged set of every widget's required printer objects — in one call.
3. `notify_status_update` deltas are shallow-merged into the reactive store.
4. The dashboard renders each registered widget inside a Neo-Brutalist frame;
   widgets read from the store and send commands through the shared client.

Because widgets declare their data needs and render from shared state, adding a
feature never requires touching the transport or other widgets.

## Backend

A FastAPI application factory (`create_app`) wires settings, logging, CORS, and a
versioned `/api` router. It exposes liveness (`/api/health`), a server-side
Moonraker reachability probe (`/api/moonraker/status`), the **firmware**
build / flash / device routes (`/api/firmware/*`), the **input-shaping**
resonance-analysis routes (`/api/shaper/*` — which vendor Klipper's
`shaper_calibrate` and add pure-numpy ports of the Shake&Tune analyses: axes-map,
spectrogram, and the machine vibrations profile), and the **motor-drivers**
routes (`/api/drivers/status` — TMC driver state aggregated from the live config +
per-driver `get_status`, annotated from a curated capability catalog
(`app/data/driver_catalog.json`) and the user's saved motor assignment;
`/api/drivers/live/{stepper}` — fast per-driver live telemetry for the monitor;
`/api/drivers/catalog` — that capability map; `/api/drivers/motors` — a 200+ motor
database baked to `app/data/motor_catalog.json`; `/api/drivers/mapping` — the persisted
stepper→motor map; `/api/drivers/recommend` — a run-current + register recommendation from
a faithful pure port of `klipper_tmc_autotune`'s `motor_constants` physics;
`/api/drivers/{config-block,apply,init,autotune,stallguard,home}` — copy-to-config and the
gated live `SET_TMC_*` / `INIT_TMC` / `AUTOTUNE_TMC` writes + sensorless-homing threshold and
test-home, all refused while printing). It is the right home for
operations that should not run in the browser — privileged file or system actions,
the live `ACCELEROMETER_MEASURE` / `TEST_RESONANCES` capture orchestration,
multi-call aggregations, or scheduled jobs — added as new route modules under
`app/api/routes/`.

## Design system

Neo-Brutalism, expressed as Tailwind tokens (`frontend/tailwind.config.ts`) and a
few component classes (`frontend/src/assets/styles/main.css`):

- **Color** — warm paper background, ink (`#111`) foreground, saturated flat
  accents (yellow/pink/cyan/lime).
- **Borders** — thick (`3px`) ink borders, near-sharp corners.
- **Shadows** — hard, blur-free offsets (`4px 4px 0 #111`); buttons "press" by
  shrinking the shadow and translating on `:active`.
- **Type** — a chunky display face (Space Grotesk) with monospace (JetBrains
  Mono) for data.

### Offline note

Fonts currently load from Google Fonts with system fallbacks, so an offline host
still renders (in fallback faces). For a fully offline install, self-host the two
fonts and replace the `<link>` in `index.html` with local `@font-face` rules.

## Internationalization (i18n)

`vue-i18n` v11 (Composition API), set up in `src/core/i18n.ts` and registered in `main.ts`. The
design mirrors the rest of the app: offline-first, extensible, and type-safe.

- **Offline-first.** `en` is bundled eagerly so first paint never waits on a network fetch (a
  printer host is usually offline). Every other locale is a dynamic `import()` chunk loaded on
  switch — combined with each widget's `defineAsyncComponent` chunk, switching to Arabic and
  opening one widget downloads only that locale's catalog for that widget.
- **Namespaced catalogs** under `src/locales/<code>/` mirror the code-split: `common`, `shell`, and
  one per widget (`firmware`, `input-shaping`, `motor-drivers`). Each JSON file carries a single
  top-level namespace key (e.g. `shell`) that is merged into the locale's messages.
- **Drop-in extensibility.** `availableLocales` is derived from which catalog folders exist, so a
  new language is *dropping in `src/locales/<code>/`* — no component or registry edits. The switcher
  (`LanguageSelect`, reusing `ComboSelect`) appears once more than one locale ships.
- **Type-safe keys.** `en` is the single source of truth; `src/types/i18n.d.ts` augments vue-i18n's
  `DefineLocaleMessage` from the `en` catalog, so `t('…')` is autocompleted and a wrong key fails
  `type-check`. Other locales are checked **structurally** against `en` by `scripts/i18n-keydiff.mjs`
  (a CI gate) — keys are often built dynamically (e.g. `t('inputShaping.grade.verdict.' + letter)`),
  which defeats eslint's `no-unused-keys`.
- **Numbers, dates, direction.** Per-locale `numberFormats` / `datetimeFormats` route values through
  `Intl` (locale separators / digit system) instead of `.toFixed()` string-gluing. Arabic pins
  Western digits (`numberingSystem: 'latn'`) — engineers cross-reference G-code and datasheets in
  `1.7 A` form. `<html lang>` / `dir` are set reactively from the active locale's metadata, so RTL
  flips with the language.
- **Tooling.** `npm run i18n:keydiff` (key-set parity, in CI) and `npm run i18n:pseudo`
  (pseudo-localization — accents + ~40% padding + brackets — to surface text-expansion / RTL overflow
  and any un-externalized strings before a translator is involved).
- **Backend messages.** Write endpoints return a `{ code, params, message }` contract: the backend
  picks a stable `code` (e.g. `motorDrivers.apply.applied`) plus interpolation `params`, and keeps an
  English `message` as a fallback. The UI renders `t(code, params)` (`applyResultText`) so localized
  copy lives in the frontend catalog, not the server. Raw upstream / validation errors (Moonraker
  failures, `field_policy` text) carry **no** `code` and surface their English text verbatim — they
  are technical strings, not product copy.

SI **unit symbols** (Hz, A, °C, Ω, Nm, mH, mm/s²) and brand / protocol / register / G-code tokens
stay Latin in every locale; only the surrounding plain-language copy is translated. All six i18n
phases (scaffolding → widgets → RTL/Arabic → backend message codes) are complete (see
[ROADMAP.md](../ROADMAP.md)).

## Conventions

- Frontend: TypeScript, Prettier (no semicolons, single quotes, width 100),
  ESLint flat config, `<script setup>` SFCs.
- Backend: type hints everywhere, Ruff (lint + format), Mypy, Pydantic v2 models.
