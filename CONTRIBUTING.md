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
