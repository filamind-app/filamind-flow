# FilaMind Flow — Backend

FastAPI service that backs the FilaMind Flow panel. It exposes health and
diagnostics endpoints today and is the home for privileged or aggregated
operations as features are added. Live printer data is read by the browser
directly from Moonraker; this service is for work that belongs server-side.

## Requirements

- Python 3.10+

## Quickstart

```bash
cd backend
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
cp .env.example .env                 # adjust FILAMIND_MOONRAKER_URL if needed
python -m app                        # serves http://localhost:8000
```

Interactive API docs: <http://localhost:8000/docs>

## Endpoints

| Method | Path                     | Purpose                                   |
| ------ | ------------------------ | ----------------------------------------- |
| GET    | `/api/health`            | Backend liveness probe.                   |
| GET    | `/api/moonraker/status`  | Server-side Moonraker reachability check. |

## Development

```bash
ruff check .          # lint
ruff format .         # format
mypy app              # type-check
pytest                # tests
```

## Configuration

All settings use the `FILAMIND_` env prefix (see `.env.example`):

| Variable                 | Default                 | Description                      |
| ------------------------ | ----------------------- | -------------------------------- |
| `FILAMIND_HOST`          | `0.0.0.0`               | Bind address.                    |
| `FILAMIND_PORT`          | `8000`                  | Bind port.                       |
| `FILAMIND_LOG_LEVEL`     | `info`                  | Log level.                       |
| `FILAMIND_MOONRAKER_URL` | `http://localhost:7125` | Moonraker base URL.              |
| `FILAMIND_CORS_ORIGINS`  | `http://localhost:5173` | Comma-separated allowed origins. |
