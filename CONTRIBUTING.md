# Contributing to FilaMind Flow

Thanks for helping build FilaMind Flow! This guide covers the dev workflow and
the conventions that keep the codebase clean.

## Development setup

```bash
# Frontend
cd frontend && npm install && npm run dev

# Backend (separate terminal)
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt && python -m app
```

## Before you push

Both suites must be green — CI runs exactly these:

```bash
# Frontend
cd frontend
npm run lint
npm run format:check
npm run type-check
npm test
npm run i18n:keydiff
npm run build

# Backend
cd backend
ruff check .
ruff format --check .
mypy app
pytest
```

Run `npm run lint:fix` and `npm run format` (frontend) or `ruff check --fix . && ruff format .`
(backend) to auto-fix most issues.

## Adding a widget (the common case)

Widgets are the unit of extension. The core never needs to change.

1. Create `frontend/src/widgets/<feature>/<Feature>Widget.vue`.
2. Register it in `frontend/src/widgets/index.ts`:

   ```ts
   registerWidget({
     id: '<feature>',                       // unique, stable
     title: '<Feature>',
     defaultSize: { w: 2, h: 1 },           // grid columns (1–4)
     subscriptions: { extruder: null },     // Moonraker objects to watch
     component: defineAsyncComponent(() => import('./<feature>/<Feature>Widget.vue')),
   })
   ```

3. Read live state from the shared store (`usePrinterStore().status`) and issue
   commands through the shared client (`moonraker.call('printer.gcode.script', …)`).

Keep components lazy (`defineAsyncComponent`) so each widget is its own chunk.

## Widget UX: explain, guide, illustrate

Every widget must be approachable to a newcomer — bare data panels aren't enough.
Build these in from the start (don't bolt them on later):

- **Explanations** — inline, collapsible help for each section (see `HelpNote.vue`).
- **Practical steps** — for any procedural tool, a numbered / guided flow with clear
  pass–fail outcomes (see the Input Shaping 🧭 Guided view).
- **Illustrations** — hand-drawn inline **SVG** diagrams (see `HelpIllo.vue`); no binary
  image assets — inline SVGs are theme-aware and diff cleanly in git.

The **Input Shaping** widget (`HelpNote` / `HelpIllo` / `help.ts` + Guided) is the
reference. Apply this to new widgets up front, and retrofit older ones over time.

## Internationalization (strings & locales)

User-facing copy is being moved into `vue-i18n` catalogs under `src/locales/` (offline-first,
extensible; see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)). While the migration is in progress
(phase-by-phase, see [ROADMAP.md](ROADMAP.md)), follow these rules so nothing regresses:

- **New user-facing text goes through `t()`**, not a hardcoded literal. Add the key to the matching
  `en` namespace JSON (`common` / `shell` / `<widget>`) — `en` is the source of truth.
- **Keys are type-checked** — `t('…')` autocompletes from the `en` catalog and a wrong key fails
  `type-check`. Use hierarchical, stable keys (e.g. `motorDrivers.format.current`).
- **Keep units and tokens Latin** — SI unit symbols (Hz, A, °C, …) and brand / protocol / register /
  G-code names (Klipper, StallGuard, `run_current`, `G28`, …) are **not** translated; only the
  surrounding prose is. Prefer `Intl`-formatted numbers (vue-i18n `numberFormats`) over `.toFixed()`.
- **Adding a language = dropping a folder** — create `src/locales/<code>/*.json` mirroring `en`,
  add the locale to `LOCALE_META` in `core/i18n.ts` (label, `dir`, optional `numberingSystem`), and
  `npm run i18n:keydiff` must pass (it enforces an exact key-set match with `en`).
- **Eyeball expansion / RTL** with `npm run i18n:pseudo` before shipping layout-sensitive copy.

## Keep the docs in step with features

When a change adds or changes a user-facing feature, an `/api` endpoint, or a
config setting, **update the docs in the same PR** — stale docs are a bug:

- **`CHANGELOG.md`** — every release (Keep a Changelog format).
- **`README.md`** — the status blurb, the **Widgets** table, and the roadmap list.
  (The release badge is dynamic — it tracks the latest GitHub Release, so no manual bump.)
- **`ROADMAP.md`** — mark the shipped phase ✅.
- **`backend/README.md`** — new or changed `/api` endpoints and `FILAMIND_*` settings.
- **`docs/ARCHITECTURE.md`** — only when the structure or data flow changes.

Keep the **repository's GitHub metadata** current too: the **About description** and
**topics** should reflect what ships today — update them with `gh repo edit` whenever a
new widget or major capability lands.

## Code style

- **Frontend** — TypeScript (no `any` where avoidable), Prettier formatting
  (no semicolons, single quotes, width 100), ESLint flat config. Components are
  `<script setup lang="ts">` and multi-word named.
- **Backend** — type hints on every function, Ruff for lint + format, Mypy for
  types. Pydantic models for all request/response shapes.
- Prefer small, single-purpose modules and descriptive names over comments that
  restate the code.

## Commits & PRs

- Use [Conventional Commits](https://www.conventionalcommits.org/): `feat:`,
  `fix:`, `docs:`, `refactor:`, `test:`, `chore:`.
- Keep PRs focused; include a short description of _why_, not just _what_.
- Ensure CI is green before requesting review.
- Merge with **rebase** (`gh pr merge --rebase`) to preserve commit authorship.

## Tracking discovered problems

Found a bug or defect while working? Don't fix it silently:

1. Open a **GitHub issue**, labeled by type (`bug`, `ci`, `chore`, `enhancement`, `ux`).
2. Fix it in a PR whose description references **`Closes #<n>`**, so merging the patch
   auto-closes the issue.

This keeps every defect traceable by type, with a patch tied to it.

## Releases

Releases publish **automatically**: pushing a `vX.Y.Z` tag triggers
[`.github/workflows/release.yml`](.github/workflows/release.yml), which creates the
GitHub Release using the annotated tag's subject as the title and the matching
`CHANGELOG.md` section as the notes. To cut a release:

```bash
# 1. Bump the version in all three places:
#    frontend/package.json · backend/pyproject.toml · backend/app/__init__.py
# 2. Add the CHANGELOG.md entry, rebuild frontend/dist, open the PR, merge.
# 3. Tag the merge commit and push the tag — the workflow does the rest:
git tag -a vX.Y.Z -m "vX.Y.Z — <summary>"
git push origin vX.Y.Z
```
