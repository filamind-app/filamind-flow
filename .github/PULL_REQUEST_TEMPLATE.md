## Summary

<!-- What does this change and why? -->

## Type

- [ ] feat — new widget or capability
- [ ] fix — bug fix
- [ ] docs / chore / refactor / test

## Checklist

- [ ] Frontend: `npm run lint && npm run format:check && npm run type-check && npm test && npm run build`
- [ ] Rebuilt + committed `frontend/dist` if any frontend source changed (the host serves the pre-built bundle; CI now fails on a stale dist)
- [ ] Backend: `ruff check . && ruff format --check . && mypy app && pytest`
- [ ] Updated `CHANGELOG.md` (Unreleased) if user-facing
- [ ] No secrets or `.env` files committed
