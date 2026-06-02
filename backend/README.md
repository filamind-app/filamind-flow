# FilaMind Flow — Backend

FastAPI service that backs the FilaMind Flow panel. It exposes health and
diagnostics, the **firmware** build / flash API, and the **input-shaping**
resonance-analysis API, and is the home for privileged or aggregated operations as
features are added. Live printer data is read by the browser directly from
Moonraker; this service is for work that belongs server-side.

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

| Method | Path                       | Purpose                                                         |
| ------ | -------------------------- | --------------------------------------------------------------- |
| GET    | `/api/health`              | Backend liveness probe.                                         |
| GET    | `/api/moonraker/status`    | Server-side Moonraker reachability check.                       |
| —      | `/api/firmware/*`          | Firmware build / flash / devices / config-profiles (Firmware Upgrade widget). |
| POST   | `/api/shaper/analyze`      | Analyze an uploaded resonance CSV → recommended shaper + curves. |
| GET    | `/api/shaper/files`        | List the resonance CSVs Klipper wrote on the host.              |
| POST   | `/api/shaper/analyze-file` | Analyze a resonance CSV already on the host (by path).          |
| POST   | `/api/shaper/live-test`    | Run `TEST_RESONANCES` on the printer and analyze the capture.   |
| POST   | `/api/shaper/noise`        | Run `MEASURE_AXES_NOISE` (motion-free) to check the sensor mount. |
| POST   | `/api/shaper/compare-belts` | Resonance-test each CoreXY belt diagonal and return both (moves the toolhead). |
| POST   | `/api/shaper/axes-map`     | Jog +X/+Y/+Z to detect the accelerometer `axes_map` orientation (moves the toolhead). |

The interactive `/docs` page is the always-current, authoritative list (the
firmware API has many routes beyond the summary above).

## Development

```bash
ruff check .          # lint
ruff format .         # format
mypy app              # type-check
pytest                # tests
```

## Configuration

All settings use the `FILAMIND_` env prefix (see `.env.example`):

| Variable                  | Default                                                          | Description                                          |
| ------------------------- | ---------------------------------------------------------------- | ---------------------------------------------------- |
| `FILAMIND_HOST`           | `0.0.0.0`                                                        | Bind address.                                        |
| `FILAMIND_PORT`           | `8000`                                                           | Bind port.                                           |
| `FILAMIND_LOG_LEVEL`      | `info`                                                          | Log level.                                           |
| `FILAMIND_MOONRAKER_URL`  | `http://localhost:7125`                                         | Moonraker base URL.                                  |
| `FILAMIND_KLIPPER_DIR`    | `~/klipper`                                                     | Klipper source tree (firmware build).                |
| `FILAMIND_KATAPULT_DIR`   | `~/katapult`                                                    | Katapult source tree (firmware flash).               |
| `FILAMIND_DATA_DIR`       | `~/printer_data/config/filamind`                               | Backend data (firmware profiles, device registry).   |
| `FILAMIND_RESONANCE_DIRS` | `/tmp,~/printer_data/config,~/printer_data/config/input_shaper` | Dirs scanned for resonance CSVs (comma-separated).   |
| `FILAMIND_CORS_ORIGINS`   | `http://localhost:5173`                                         | Comma-separated allowed origins.                     |
