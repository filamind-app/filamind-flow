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

- **Explanations** — the shared **`HelpDrawer`** (`components/ui/HelpDrawer.vue`): a single
  `❓ Help` button that opens one off-canvas guide (how-to-read steps + every topic with its
  illustration + the glossary). This is the **adopted pattern** — do not hand-roll inline
  `<details>` / per-section "what's this?" notes. Each widget supplies a `help.ts`
  (`HELP_TOPICS` / `HELP_ILLO` / `GLOSSARY_KEYS`) + a local `HelpIllo.vue`.
- **Practical steps** — for any procedural tool, a numbered / guided flow with clear
  pass–fail outcomes (see the Input Shaping 🧭 Guided view).
- **Illustrations** — hand-drawn inline **SVG** diagrams (see `HelpIllo.vue`); no binary
  image assets — inline SVGs are theme-aware and diff cleanly in git.
- **Error reporting** — wherever a widget shows an error message, drop the shared
  **`ReportErrorButton`** (`components/feedback/ReportErrorButton.vue`) next to it: a `⚐ Report`
  control that opens a pre-filled GitHub bug report from that exact error text (plus an
  auto-captured screenshot and diagnostics). The shared `LogPane` exposes this via its
  `reportable` prop, so operation logs get it for free.

The **Board Topology** / **Input Shaping** widgets are the reference for the `HelpDrawer`
wiring + `help.ts` shape. Apply this to new widgets up front.

> **Enforced in CI:** `src/core/__tests__/widgets.spec.ts` fails the build if any registered
> widget lacks a translated sidebar entry (`shell.widgets.<id>.{title,description}`) or doesn't
> render the shared `<HelpDrawer>`. The 7-locale parity test then requires the sidebar entry in
> every language. These rules can't be skipped — a new widget won't merge without them.

## Internationalization (strings & locales)

All user-facing copy lives in `vue-i18n` catalogs under `src/locales/` (offline-first, extensible;
see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)). The UI ships fully localized in **7 languages**
(en · ar · de · zh-Hans · fr · es · ru, Arabic RTL); keep it that way — follow these rules so
nothing regresses:

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

## Contributing hardware catalog data

The Hardware Browser is backed by a curated catalog. Its editable source — `hardware.json` — is
**git-ignored** (kept locally by maintainers); only the compiled, read-only `hardware.sqlite` ships
in the repo. So new parts come in as **submissions** that a maintainer merges, rather than direct
edits to the catalog.

**For contributors:** open the app → **Hardware Browser → ➕ Suggest a part**, pick the part type,
fill in what you know, and submit. It opens a pre-filled GitHub issue (label `catalog-submission`)
with a JSON fragment — review it and submit on GitHub. No account data leaves the app; nothing is
posted automatically. You can also file the [Catalog submission](.github/ISSUE_TEMPLATE/catalog-submission.yml)
issue form by hand.

**For maintainers:** review the submitted fragment, then merge it with:

```bash
python scripts/apply_submission.py fragment.json   # validate → merge into hardware.json → rebuild sqlite
#   --type <t>   override the inferred part type      --force   replace an existing entry by id
#   --no-build   merge only (skip the sqlite rebuild)
```

It validates the required fields and shapes, dedupes by id (manufacturers by name), merges into the
right array (`motors` / `drivers` / `boards` / `hosts` / `manufacturers`) or `catalog[<category>]`,
and reruns `build_hardware_db.py`. Review the `hardware.sqlite` diff and commit it. The submission
shape is mirrored in the app's `frontend/src/widgets/hardware-browser/contributeSchema.ts`.

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
