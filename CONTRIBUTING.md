# Contributing to FilaMind Flow

Thanks for helping build FilaMind Flow. This guide walks through the dev workflow and the conventions that keep the codebase clean. Most contributions are new widgets, so there's a section dedicated to that below.

## Development setup

You'll run two processes: the Vite frontend and the Python backend. Open a terminal for each.

```bash
# Frontend
cd frontend && npm install && npm run dev

# Backend (separate terminal)
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt && python -m app
```

## Before you push

CI runs the two suites below, and both have to be green. Run them locally first.

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

Most lint and formatting problems fix themselves. On the frontend, run `npm run lint:fix` and `npm run format`. On the backend, run `ruff check --fix . && ruff format .`.

## Adding a widget (the common case)

Widgets are the unit of extension here, and you should be able to add one without touching the core.

First, create the component at `frontend/src/widgets/<feature>/<Feature>Widget.vue`.

Then register it in `frontend/src/widgets/index.ts`:

```ts
registerWidget({
  id: '<feature>',                       // unique, stable
  title: '<Feature>',
  defaultSize: { w: 2, h: 1 },           // grid columns (1–4)
  subscriptions: { extruder: null },     // Moonraker objects to watch
  component: defineAsyncComponent(() => import('./<feature>/<Feature>Widget.vue')),
})
```

Inside the widget, read live state from the shared store with `usePrinterStore().status`, and send commands through the shared client with `moonraker.call('printer.gcode.script', …)`.

Keep the component lazy by loading it with `defineAsyncComponent`, as shown above. That way each widget ends up in its own chunk.

## Widget UX: explain, guide, illustrate

A bare data panel isn't enough. Every widget should make sense to someone seeing it for the first time, and that's much easier to get right if you build it in from the start rather than bolting it on later. Four things matter here.

**Explanations.** Use the shared `HelpDrawer` (`components/ui/HelpDrawer.vue`). It's a single `❓ Help` button that opens one off-canvas guide covering the how-to-read steps, every topic with its illustration, and the glossary. This is the adopted pattern, so don't hand-roll inline `<details>` blocks or per-section "what's this?" notes. Each widget supplies a `help.ts` (with `HELP_TOPICS`, `HELP_ILLO`, and `GLOSSARY_KEYS`) plus a local `HelpIllo.vue`.

**Practical steps.** Any procedural tool needs a numbered or guided flow with clear pass/fail outcomes. The Input Shaping 🧭 Guided view is a good example to follow.

**Illustrations.** Diagrams are hand-drawn inline SVG, the way `HelpIllo.vue` does it. Don't add binary image assets. Inline SVGs are theme-aware and they diff cleanly in git.

**Error reporting.** Wherever a widget shows an error message, put the shared `ReportErrorButton` (`components/feedback/ReportErrorButton.vue`) next to it. It's a `⚐ Report` control that opens a pre-filled GitHub bug report from that exact error text, along with an auto-captured screenshot and diagnostics. The shared `LogPane` exposes this through its `reportable` prop, so operation logs get it for free.

The Board Topology and Input Shaping widgets are the reference for the `HelpDrawer` wiring and the `help.ts` shape. Look at those when you wire up a new widget.

> **Enforced in CI:** `src/core/__tests__/widgets.spec.ts` fails the build if a registered widget is missing a translated sidebar entry (`shell.widgets.<id>.{title,description}`) or doesn't render the shared `<HelpDrawer>`. On top of that, the 7-locale parity test requires the sidebar entry in every language. You can't skip these, so a new widget won't merge without them.

## Internationalization (strings & locales)

All user-facing copy lives in `vue-i18n` catalogs under `src/locales/`. The setup is offline-first and extensible; see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the details. The UI ships fully localized in 7 languages: en, ar, de, zh-Hans, fr, es, and ru, with Arabic in RTL. Keep it that way. A few rules keep it from regressing.

New user-facing text always goes through `t()`, never a hardcoded literal. Add the key to the matching `en` namespace JSON (`common`, `shell`, or `<widget>`). `en` is the source of truth.

Keys are type-checked. `t('…')` autocompletes from the `en` catalog, and a wrong key fails `type-check`. Use hierarchical, stable keys like `motorDrivers.format.current`.

Keep units and tokens Latin. SI unit symbols such as Hz, A, and °C are not translated, and neither are brand, protocol, register, or G-code names like Klipper, StallGuard, `run_current`, and `G28`. Only the surrounding prose gets translated. Prefer `Intl`-formatted numbers (vue-i18n `numberFormats`) over `.toFixed()`.

Adding a language is mostly a matter of dropping in a folder. Create `src/locales/<code>/*.json` mirroring `en`, add the locale to `LOCALE_META` in `core/i18n.ts` (its label, `dir`, and optional `numberingSystem`), and make sure `npm run i18n:keydiff` passes. That check enforces an exact key-set match with `en`.

Before you ship layout-sensitive copy, eyeball it for expansion and RTL issues with `npm run i18n:pseudo`.

## Keep the docs in step with features

When a change adds or changes a user-facing feature, an `/api` endpoint, or a config setting, update the docs in the same PR. Stale docs are a bug. Depending on what you changed, that means:

- **`CHANGELOG.md`** — every release (Keep a Changelog format).
- **`README.md`** — the status blurb, the Widgets table, and the roadmap list. The release badge is dynamic, tracking the latest GitHub Release, so it needs no manual bump.
- **`ROADMAP.md`** — mark the shipped phase ✅.
- **`backend/README.md`** — new or changed `/api` endpoints and `FILAMIND_*` settings.
- **`docs/ARCHITECTURE.md`** — only when the structure or data flow changes.

Keep the repository's GitHub metadata current too. The About description and topics should reflect what ships today, so update them with `gh repo edit` whenever a new widget or major capability lands.

## Contributing hardware catalog data

The Hardware Browser is backed by a curated catalog. Its editable source, `hardware.json`, is git-ignored and kept locally by maintainers; only the compiled, read-only `hardware.sqlite` ships in the repo. Because of that, new parts come in as submissions that a maintainer merges, not as direct edits to the catalog.

**For contributors:** open the app, then go to **Hardware Browser → ➕ Suggest a part**. Pick the part type, fill in what you know, and submit. That opens a pre-filled GitHub issue (label `catalog-submission`) containing a JSON fragment. Review it and submit on GitHub. No account data leaves the app, and nothing is posted automatically. If you'd rather, you can file the [Catalog submission](.github/ISSUE_TEMPLATE/catalog-submission.yml) issue form by hand.

**For maintainers:** review the submitted fragment, then merge it:

```bash
python scripts/apply_submission.py fragment.json   # validate → merge into hardware.json → rebuild sqlite
#   --type <t>   override the inferred part type      --force   replace an existing entry by id
#   --no-build   merge only (skip the sqlite rebuild)
```

The script validates the required fields and shapes, dedupes by id (manufacturers by name), and merges into the right array (`motors`, `drivers`, `boards`, `hosts`, `manufacturers`) or into `catalog[<category>]`. Then it reruns `build_hardware_db.py`. Review the `hardware.sqlite` diff and commit it. The submission shape is mirrored in the app at `frontend/src/widgets/hardware-browser/contributeSchema.ts`.

## Code style

**Frontend.** TypeScript, avoiding `any` where you can. Prettier handles formatting (no semicolons, single quotes, width 100), and ESLint uses the flat config. Components are `<script setup lang="ts">` and have multi-word names.

**Backend.** Type hints on every function. Ruff for lint and format, Mypy for types. Use Pydantic models for all request and response shapes.

Across both, prefer small, single-purpose modules and descriptive names over comments that just restate the code.

## Commits & PRs

- Use [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`.
- Keep PRs focused, and say _why_ in the description, not just _what_.
- Make sure CI is green before requesting review.
- Merge with rebase (`gh pr merge --rebase`) to preserve commit authorship.

## Tracking discovered problems

If you find a bug or defect while working, don't fix it silently. Two steps:

1. Open a GitHub issue and label it by type (`bug`, `ci`, `chore`, `enhancement`, `ux`).
2. Fix it in a PR whose description references `Closes #<n>`, so merging the patch auto-closes the issue.

This keeps every defect traceable by type, with a patch tied to it.

## Releases

Releases publish automatically. Pushing a `vX.Y.Z` tag triggers [`.github/workflows/release.yml`](.github/workflows/release.yml), which creates the GitHub Release using the annotated tag's subject as the title and the matching `CHANGELOG.md` section as the notes.

To cut a release:

```bash
# 1. Bump the version in all three places:
#    frontend/package.json · backend/pyproject.toml · backend/app/__init__.py
# 2. Add the CHANGELOG.md entry, rebuild frontend/dist, open the PR, merge.
# 3. Tag the merge commit and push the tag — the workflow does the rest:
git tag -a vX.Y.Z -m "vX.Y.Z — <summary>"
git push origin vX.Y.Z
```
