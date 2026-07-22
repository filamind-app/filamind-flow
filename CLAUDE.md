# Working on FilaMind Flow

FilaMind Flow is a control panel for Klipper / Moonraker printers: a Vue 3 + Vite + Tailwind 4
frontend and a FastAPI backend, organised as independent widgets. It runs beside Moonraker on the
printer host and can also be hosted inside another web UI.

Two companion apps exist in the same organization: `filamind-3d` (a web control UI served from the
printer) and `filamind-screen` (a native touch app for the printer's own display). Both are
**experimental**, and so are the Flow widgets that `filamind-3d` unlocks — Material Brain, Tuning,
Pre-Print Check, Known-Good Pack and the Rules Engine. They render an install-required gate until
FilaMind 3d is detected, and carry an experimental note once it is.

## Layout

```
frontend/          Vue 3 SPA. Widgets live in src/widgets/<id>/.
frontend/dist/     The built bundle, COMMITTED. CI rebuilds it if it drifts.
frontend/src/locales/<code>/   19 locales, held at parity with `en` by a CI key-diff gate.
backend/app/       FastAPI. Routes in api/routes/, logic in services/, schemas in models/.
```

## Before you push

Run the full CI command set. Running a subset is the usual cause of a red run.

```bash
# backend
ruff check . && ruff format --check . && mypy app && pytest -m "not e2e" && pytest -m e2e

# frontend
npm run lint && npm run type-check && npm test && npm run i18n:keydiff && npm run format:check && npm run build
```

`prettier --check` runs as its own CI step, separate from eslint, and a locally installed prettier
may format differently from the lockfile's — pin the version if `format:check` disagrees with CI.

## Shipping

Every shipped PR moves three files in lockstep and then pushes a tag:

```
frontend/package.json      "version": "X.Y.Z"
backend/app/__init__.py    __version__ = "X.Y.Z"
CHANGELOG.md               ## [X.Y.Z] - YYYY-MM-DD
git tag -a vX.Y.Z && git push origin vX.Y.Z
```

Documentation moves in the same PR as the change: README, ROADMAP, `backend/README.md`, CHANGELOG,
and ARCHITECTURE if the structure moved.

Work consolidates into `main`, merged manually once CI is green
(`gh pr merge <n> --rebase --delete-branch`) — never GitHub auto-merge.

**The `[skip ci]` trap.** When `frontend/dist` drifts, CI commits
`chore(ci): rebuild frontend/dist [skip ci]` onto the branch. With that commit at HEAD,
`gh pr checks` reports "no checks reported", which can hide a *failing* run — confirm with
`gh run list --branch <b> --json workflowName,conclusion` before merging. And if that commit ends up
being the tagged one, `release.yml` is skipped and the release must be published by hand with
`gh release create`.

## Gotchas

- A FastAPI `response_model` silently strips fields not declared on the schema. Adding a field to a
  service dict means adding it to `models/schemas.py` too — and a test that calls the service
  function directly will not catch the omission.
- A widget's data may be served whether or not its companion app is installed; gate on the suite
  signal, not on assumptions about the host.

## Rules

- Commit messages, PR bodies and issue comments are purely technical English. No team-chat content,
  no notes about how a change was decided.
- Only the three maintainers listed in the README may appear as commit authors. No
  `Co-Authored-By`, no tool-attribution trailers.
- **Never close a user's issue**, even after fixing it. Reply as a human maintainer explaining the
  cause, the change, and the version that carries it, then leave it open until the reporter
  confirms.
- **Never hand an end user a shell command.** Missing host dependencies are installed by the
  install/update flow.
- Features target the general Klipper and Moonraker surface, not one printer model.
- Do not ship configuration nobody asked for.

Maintainers: the full handbook, the research corpus and the current handoff live in the private
`filamind-app/filamind-internal` repo.
