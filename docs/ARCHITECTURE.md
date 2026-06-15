# Architecture

This document explains how FilaMind Flow is put together and why. For a quick
start see the root [README](../README.md).

## Goals

1. **Integrate** with Klipper, Moonraker, Mainsail, and Fluidd without forking any
   of them.
2. **Stay light** on the printer host.
3. **Grow** through small, independent features.

## Integration model

The panel is a standalone SPA that talks directly to Moonraker. We link it from
the Mainsail sidebar. Fluidd has no custom-link API yet, so there you reach it by
URL instead. Other ecosystem tools settle on the same pattern for a simple reason:
there is no stable third-party plugin API inside Mainsail or Fluidd. A sibling page
that shares the same Moonraker instance is the clean, durable approach.

```
Browser (phone / desktop)
  └─ FilaMind Flow SPA ──REST──► Moonraker :7125 ──► Klipper (MCU)
                       └──WS───► Moonraker :7125
  └─ FilaMind Flow SPA ──REST──► FilaMind backend :8000 ──► Moonraker (server-side)
```

## Resource footprint

The **frontend** is built on a developer machine and deployed as static files,
served by the same nginx that already serves Mainsail and Fluidd. At runtime the
printer host only hands out a few static assets; the app itself runs in the browser
on the client device. So the cost on the Pi is roughly the cost of serving static
files.

The **backend** is a single async Uvicorn process. Idle, it sits around 30-60 MB
of RAM and close to 0% CPU, comparable to Moonraker's own footprint. It is
event-driven, with no polling loops.

**WebSocket** subscriptions are kept to just the union of printer objects the
active widgets actually need. That keeps notification traffic minimal.

## Frontend layers

```
src/
├─ core/
│  ├─ moonraker/   # transport: reconnecting JSON-RPC WS client + types + config
│  ├─ registry/    # extensibility: the widget registry
│  ├─ store/       # state: Pinia mirror of Moonraker status
│  └─ i18n.ts      # i18n: catalog loading, locale detection, switching
├─ components/     # presentation: app shell + dashboard (design-system driven)
├─ widgets/        # features: 10 self-registering widgets (Machine Doctor · Firmware Manager · Input Shaping · Motor Drivers · Config Editor · Macro Designer · Board Topology · Max-Flow · Config Templates · Hardware Browser)
├─ locales/        # i18n message catalogs, one folder per language (en bundled; others lazy)
└─ assets/styles/  # Neo-Brutalist design tokens + component classes
```

Dependencies point inward. `widgets` and `components` depend on `core`, and `core`
depends on nothing app-specific. That keeps the transport and registry reusable and
testable in isolation.

### MoonrakerClient

A single long-lived client (`core/moonraker/client.ts`) owns the WebSocket:

- **Request/response** — each `call()` gets an incrementing id. Responses resolve
  the matching pending promise, with a timeout as a safety net.
- **Notifications** — `notify_*` messages are fanned out to listeners registered
  by method name. The store, for example, listens for `notify_status_update`.
- **Reconnection** — exponential backoff. On reconnect the remembered subscription
  set is re-sent, so widgets keep receiving updates transparently.

### Widget lifecycle

1. At startup, `registerWidgets()` calls `registerWidget(...)` for each feature.
2. On connect, the store subscribes to `widgetRegistry.aggregateSubscriptions()`
   — the merged set of every widget's required printer objects — in one call.
3. `notify_status_update` deltas are shallow-merged into the reactive store.
4. The dashboard renders each registered widget inside a Neo-Brutalist frame.
   Widgets read from the store and send commands through the shared client.

Because widgets declare their data needs and render from shared state, adding a
feature never means touching the transport or the other widgets.

## Backend

A FastAPI application factory (`create_app`) wires settings, logging, CORS, and a
versioned `/api` router. From there it exposes a handful of endpoint groups.

Liveness lives at `/api/health`, and a server-side Moonraker reachability probe at
`/api/moonraker/status`. The **firmware** routes (`/api/firmware/*`) handle build,
flash, and device operations.

The **input-shaping** resonance-analysis routes are at `/api/shaper/*`. They vendor
Klipper's `shaper_calibrate` and add pure-numpy resonance analyses of their own:
axes-map, spectrogram, and the machine vibrations profile.

The **motor-drivers** routes cover several jobs. `/api/drivers/status` aggregates
TMC driver state from the live config plus each driver's `get_status`, annotated
from the unified hardware catalog's driver capability map (`drivers[].caps` in the
hardware catalog, served as `DriverInfo`) and the user's saved motor assignment.
`/api/drivers/live/{stepper}` gives fast per-driver live telemetry for the monitor.
`/api/drivers/catalog` returns that capability map, and `/api/drivers/motors` serves
a 600+ motor catalog from the same hardware reference. `/api/drivers/mapping` is the
persisted stepper→motor map, and `/api/drivers/recommend` produces a run-current and
register recommendation from a built-in `motor_constants` physics model. Finally,
`/api/drivers/{config-block,apply,init,autotune,stallguard,home}` handle copy-to-config
and the gated live writes — `SET_TMC_*`, `INIT_TMC`, `AUTOTUNE_TMC` — plus the
sensorless-homing threshold and test-home. All of those writes are refused while the
printer is running.

The **config** routes are read-only for now. `/api/config/files` and
`/api/config/file` list and parse the live `printer.cfg` and its includes through the
round-trip `klipper_config` engine, turning them into sections → params with
validation issues. This is the keystone of the planned Config Editor.

The backend is the right home for anything that should not run in the browser:
privileged file or system actions, the live `ACCELEROMETER_MEASURE` /
`TEST_RESONANCES` capture orchestration, multi-call aggregations, or scheduled jobs.
Each arrives as a new route module under `app/api/routes/`.

### Hardware database (`/api/hardware/*`)

This is a curated, read-only reference dataset. It compiles into
`app/data/reference/hardware.sqlite` (~7 MB), built from a local source by
`scripts/build_hardware_db.py`, which is not in the repo. At import time it is
reconstructed once into a module-global dict (`reference_data.py`) and is immutable
after that — handlers only ever read, so there are no locks.

At build time the raw rows (`items[]`) are deduped and enriched into canonical entity
arrays: `boards`, `drivers`, `motors`, `hosts`, and a generic `catalog` covering nine
more categories. Each entity carries its specs along with a copyable Klipper config
snippet — a board pin-map, a `[tmcXXXX]` driver block, a recommended motor
`run_current`, an `[mcu host]` block, and so on. Per type there is a small
`*_search.py` that filters and paginates down to lightweight summaries, plus two
routes: a paginated list and a `/{id}` full record. A `manufacturers` directory and a
`categories` listing round it out. CI guards keep the data honest with per-category
floors so a regen can't gut a category, data-hygiene checks, and lossless
port-aggregation locks.

**Performance (DB-1):** lists, `id→entity` index dicts, and a precomputed per-item
search haystack are all built once at load. So every `*_by_id` is O(1), and the flat
free-text search never rebuilds its haystacks per request. The read-only
`/api/hardware/*` responses carry a weak `ETag` and `Cache-Control`, returning 304 on
a match and busting on redeploy.

**Linking backbone (DB-2):** `hardware_links.py` is a pure module that turns the
once-islanded relationships into a precomputed in-memory graph, built once at load. It
canonicalises manufacturers, giving each a stable `manufacturer_id` plus auto-derived
aliases so variant spellings collapse to one id, with junk and placeholders excluded.
It promotes the MCU to a first-class entity by parsing board `specs.MCU` through a
chip-family whitelist down to a canonical part. And it builds an adjacency map keyed by
composite `<type>:<id>` ids, which matters because ids are not unique across types —
`sovol-sv08` is both a board and a host. That graph powers
`GET /api/hardware/manufacturers[/{id}]`, `/mcus[/{id}]`, a generic
`GET /api/hardware/{type}/{id}/related`, and `?expand=related` on the detail routes,
all O(1). A widget can pull an entity and everything related to it in a single call. A
CI edge-validator proves the graph has no dangling edges.

The Hardware Browser surfaces this graph (DB-3a). Every entity's detail shows clickable
cross-link chips — manufacturer, MCU, drivers — that deep-link to the related entity,
and **Brands** and **MCUs** tabs let you browse outward from a maker or a chip. The five
detail panels share one `EntityCatalog.vue` shell that handles search, list, pagination,
expand, copy, and deep-link. Each panel is a thin wrapper supplying a `fetchPage` closure
plus its own summary and detail slots (DB-3b). The shell's `#facets` slot carries each
panel's filters — class, NEMA, kind, manufacturer — backed by `GET /api/hardware/facets`
(DB-3c). See the Hardware-DB section in [ROADMAP.md](../ROADMAP.md).

## Design system

Neo-Brutalism, expressed as Tailwind tokens (`frontend/tailwind.config.ts`) and a
few component classes (`frontend/src/assets/styles/main.css`):

- **Color** — warm paper background, ink (`#111`) foreground, saturated flat
  accents (mocha-brown brand/pink/cyan/lime).
- **Borders** — thick (`3px`) ink borders, near-sharp corners.
- **Shadows** — hard, blur-free offsets (`4px 4px 0 #111`); buttons "press" by
  shrinking the shadow and translating on `:active`.
- **Type** — a chunky display face (Space Grotesk) with monospace (JetBrains
  Mono) for data.

### Theming

Every visual token is a CSS custom property, so the whole app restyles from a single
switch. The Tailwind tokens reference those variables
(`ink: 'rgb(var(--c-ink) / <alpha-value>)'`, `boxShadow` → `var(--nb-shadow*)`,
`borderRadius.brutal` → `var(--nb-radius)`). That means every existing utility —
`bg-paper`, `border-ink`, `bg-brand-cyan`, `shadow-brutal`, `rounded-brutal` —
recolors per theme with no component edits. `main.css` holds `:root` for the Light
defaults plus one `[data-theme="…"]` block per theme.

- **Themes (7):** `light` (default — daylight brutalism, warm cream + mocha-brown brand accent),
  `neon` (deep violet + electric glow), `midnight` (navy ops deck), `dark` (steel slate),
  `ocean` (abyssal teal), `sunset` (dusk plum), and `contrast` (near-black/white, a11y).
  All seven are calibrated palettes. Each uses a two-tier accent ramp: status-badge
  colors are held at a depth where their text passes WCAG, while signal colors run
  brighter for charts and danger. An automated contrast test guards this and fails the
  build on a regression (v0.226.0). The setup mirrors the i18n design: `core/theme.ts`
  handles the registry, detection, `localStorage` persistence, and the reactive
  `data-theme`; a `ThemeMenu` header control gives live preview; and a no-flash inline
  `<head>` script applies the saved theme before first paint. Adding a new theme means
  one `[data-theme]` block in `main.css`, a `THEME_META` entry, and locale names — the
  three added in v0.226.0 followed exactly that path.
- Theme is **orthogonal to locale/RTL** — the `:lang(ar)`/`[dir=rtl]` rules are independent.
- SVG charts read the same token variables (not hardcoded hex), so they recolor with the theme.

### Offline note

Fonts currently load from Google Fonts with system fallbacks, so an offline host
still renders (in fallback faces). For a fully offline install, self-host the two
fonts and replace the `<link>` in `index.html` with local `@font-face` rules.

## Internationalization (i18n)

`vue-i18n` v11 (Composition API), set up in `src/core/i18n.ts` and registered in
`main.ts`. The design mirrors the rest of the app: offline-first, extensible, and
type-safe.

- **Offline-first.** `en` is bundled eagerly so first paint never waits on a network
  fetch, since a printer host is usually offline. Every other locale is a dynamic
  `import()` chunk loaded on switch. Combined with each widget's
  `defineAsyncComponent` chunk, switching to Arabic and opening one widget downloads
  only that locale's catalog for that widget.
- **Namespaced catalogs** under `src/locales/<code>/` mirror the code-split: `common`,
  `shell`, and one per widget (`firmware`, `input-shaping`, `motor-drivers`,
  `config-editor`, `macro-designer`, `board-topology`, `max-flow`, `config-templates`,
  `hardware-browser`). Each JSON file carries a single top-level namespace key (such as
  `shell`) that is merged into the locale's messages.
- **Drop-in extensibility.** `availableLocales` is derived from which catalog folders
  exist, so adding a language is just dropping in `src/locales/<code>/` — no component
  or registry edits. The switcher (`LanguageSelect`, reusing `ComboSelect`) appears
  once more than one locale ships.
- **Type-safe keys.** `en` is the single source of truth. `src/types/i18n.d.ts`
  augments vue-i18n's `DefineLocaleMessage` from the `en` catalog, so `t('…')` is
  autocompleted and a wrong key fails `type-check`. Other locales are checked
  structurally against `en` by `scripts/i18n-keydiff.mjs`, a CI gate. Keys are often
  built dynamically — for example `t('inputShaping.grade.verdict.' + letter)` — which
  defeats eslint's `no-unused-keys`.
- **Numbers, dates, direction.** Per-locale `numberFormats` and `datetimeFormats` route
  values through `Intl` for locale separators and digit systems instead of gluing
  strings with `.toFixed()`. Arabic pins Western digits (`numberingSystem: 'latn'`),
  since engineers cross-reference G-code and datasheets in `1.7 A` form. `<html lang>`
  and `dir` are set reactively from the active locale's metadata, so RTL flips with the
  language.
- **Tooling.** `npm run i18n:keydiff` checks key-set parity in CI. `npm run i18n:pseudo`
  runs pseudo-localization — accents, ~40% padding, brackets — to surface
  text-expansion or RTL overflow and any un-externalized strings before a translator is
  involved.
- **Backend messages.** Write endpoints return a `{ code, params, message }` contract.
  The backend picks a stable `code` (such as `motorDrivers.apply.applied`) plus
  interpolation `params`, and keeps an English `message` as a fallback. The UI renders
  `t(code, params)` (`applyResultText`) so localized copy lives in the frontend catalog,
  not the server. Raw upstream or validation errors — Moonraker failures, `field_policy`
  text — carry no `code` and surface their English text verbatim. They are technical
  strings, not product copy.

SI unit symbols (Hz, A, °C, Ω, Nm, mH, mm/s²) and brand, protocol, register, and
G-code tokens stay Latin in every locale; only the surrounding plain-language copy is
translated. All six i18n phases (scaffolding → widgets → RTL/Arabic → backend message
codes) are complete (see [ROADMAP.md](../ROADMAP.md)).

## Conventions

- Frontend: TypeScript, Prettier (no semicolons, single quotes, width 100),
  ESLint flat config, `<script setup>` SFCs.
- Backend: type hints everywhere, Ruff (lint + format), Mypy, Pydantic v2 models.
