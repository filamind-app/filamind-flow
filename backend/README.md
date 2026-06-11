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
| POST   | `/api/shaper/excitate`     | Hold a frequency (sustain) to find what rattles → spectrogram + energy timeline (moves the toolhead in place). |
| POST   | `/api/shaper/vibrations-profile` | Sweep speed × motor-angle → smoothest/worst speeds, motor symmetry, motor resonance (moves the toolhead for minutes). |
| GET    | `/api/shaper/archive`      | List the saved runs (captures + generated configs) in the on-host archive. |
| GET    | `/api/shaper/archive/{id}` | One archived run + its inline config text.                      |
| GET    | `/api/shaper/archive/{id}/file/{name}` | Download a CSV / config stored in a run.            |
| DELETE | `/api/shaper/archive/{id}` | Delete an archived run (folder + index entry).                  |
| POST   | `/api/shaper/archive/save-config` | Save a generated `[input_shaper]` config to the archive. |
| POST   | `/api/shaper/archive/save-file` | Copy an existing host resonance CSV into the archive.      |
| GET    | `/api/drivers/status`      | Live TMC stepper-driver inventory: current / mode / microsteps / StallGuard / temperature / health + each axis's homing method (physical / sensorless / probe / …, from `endstop_pin`) + the effective run-current cap (`current_cap` = min(model code cap, motor rating)), each annotated with its model's catalog facts (Motor Drivers widget). |
| GET    | `/api/drivers/endstops`    | Live endstop trigger state (open / TRIGGERED), actively queried on demand — for the physical-homing panel. |
| GET    | `/api/drivers/live/{stepper}` | Fast live telemetry for one driver (temperature / SG_RESULT / CS_ACTUAL / faults) for the live monitor. |
| GET    | `/api/drivers/catalog`     | The curated TMC driver capability map (interface, current cap, chopper modes, StallGuard field, sensorless / temperature) keyed by model. |
| GET    | `/api/drivers/motors`      | The stepper-motor catalog (datasheet parameters) for the motor picker — served from the unified hardware database. |
| GET    | `/api/drivers/mapping`     | The saved stepper → motor assignments. |
| POST   | `/api/drivers/mapping`     | Assign a catalogued motor to a stepper (empty `motor_model` clears it). |
| POST   | `/api/drivers/recommend`   | Recommend a run current + StealthChop/SpreadCycle registers for a motor (compute-only; faithful `motor_constants` port). |
| POST   | `/api/drivers/config-block`| Render a printer.cfg override block to copy (no write). |
| POST   | `/api/drivers/apply`       | Write tuning live via `SET_TMC_CURRENT` / `SET_TMC_FIELD` (refused while printing; validated). |
| POST   | `/api/drivers/init`        | `INIT_TMC` — re-apply the stepper's configured registers (revert a live apply). |
| POST   | `/api/drivers/autotune`    | Drive `AUTOTUNE_TMC` if the `klipper_tmc_autotune` add-on is installed for the stepper. |
| POST   | `/api/drivers/stallguard`  | Set a StallGuard threshold (`sgthrs` / `sgt` / `sg4_thrs`) — sensorless-homing sensitivity (gated + server-clamped). |
| GET    | `/api/drivers/field-policy/{model}` | The editable-register policy for a model — which fields the editor may expose, with control type + clamp range. |
| POST   | `/api/drivers/field`       | Write one editable TMC register field live via `SET_TMC_FIELD` (gated; server-side allowlist + per-field clamp; velocity thresholds sent as mm/s). |
| POST   | `/api/drivers/coolstep`    | Enable CoolStep with a vetted register set (semin/semax/seup/sedn/seimin) or disable it — a single gated toggle. |
| POST   | `/api/drivers/home`        | Home one axis (`G28 <axis>`) as a sensorless test — moves the toolhead (gated). |
| GET    | `/api/drivers/motors-sync` | Whether the `motors_sync` add-on is installed. |
| POST   | `/api/drivers/motors-sync` | Run `SYNC_MOTORS` / `SYNC_MOTORS_CALIBRATE` (multi-motor phase alignment) — moves the toolhead (gated). |
| GET    | `/api/reference/stallguard` (+ `/{driver}`) | Per-driver StallGuard slip-detection tuning constants (base + overrides; `{driver}` = merged effective set + SG field). Static reference data. |
| GET    | `/api/reference/hotends`   | Hotend melt-zone / expected max-flow / test presets. |
| GET    | `/api/reference/boards`    | Board + MCU identification patterns. |
| GET    | `/api/reference/macros`    | Built-in Klipper calibration macro definitions. |
| GET    | `/api/config/files`        | List the editable config files (`.cfg` / `.conf`) under Moonraker's `config` root (Config Editor). |
| GET    | `/api/config/file`         | Parse one config file (`?filename=`) into a structured view: sections → params + validation issues (read-only). |
| POST   | `/api/config/save`         | Back up then overwrite one config file (refused while printing; auto-backup to `filamind-backups/`). |
| POST   | `/api/config/restart`      | `FIRMWARE_RESTART` to apply a saved config (refused while printing). |
| POST   | `/api/maxflow/plan`        | Preview the max-flow test ramp (flow → feedrate per step + StallGuard field); pure compute, no actuation. |
| POST   | `/api/maxflow/run`         | Run the live max-flow test (heat + extrude + sample StallGuard); preflight (chopper-mode/StallGuard) + SG4 bias-floor + ≥180 °C; refused while printing; heater always cut. |
| GET    | `/api/topology`            | Host → MCU topology from the live config: the host SBC (identified via `/machine/system_info`, linked to a catalog host; flagged `integrated_into_board_id` when its SoC matches the primary mainboard's declared onboard SBC) + each MCU's connection (CAN/USB/UART) + chip (linked to a catalog MCU) + a suggested board (serial-signature match, strengthened by a used-pin-set fingerprint vs each board's pin-map) + the components (steppers/drivers/heaters/fans/sensors) on it, attached by each pin's chip prefix. A saved per-MCU override (below) is re-applied as a `confirmed` board. |
| POST   | `/api/topology/override`   | Confirm / override the catalog board for one MCU (keyed by its config section name). Validates the `board_id` against the catalog; persisted on the host and applied to every read. |
| POST   | `/api/topology/override/clear` | Remove an MCU's board override (revert to the auto suggestion). |
| GET    | `/api/topology/pin-atlas/{mcu_name}` | The used-vs-free pin map of an MCU's resolved board (honouring overrides) + a wiring-health scan: pins driven by >1 config section (`double_assign`) and board electronics caveats bound to a used pin (`caveat`). `available=false` when the board has no pin-map. |
| POST   | `/api/topology/snapshot`   | Save the current topology as the hardware baseline (per-MCU board / chip / connection / component-count, keyed by section name) for later change detection. |
| GET    | `/api/topology/snapshot/diff` | Compare the live topology to the saved baseline → structured changes (MCU added/removed, board/connection/chip/component-count changed). `has_baseline=false` until a snapshot is saved. |
| POST   | `/api/macro/simulate`      | Offline G-code simulator: macro `{ params.X }` substitution → path / bounds / totals / time / timeline; pure, no printer. |
| GET    | `/api/macro/live`          | The printer's own installed `[gcode_macro]` definitions from the live `configfile` (body + description + discovered `{ params.X }` + `variable_*`), to load into the editor and simulate. `reachable=false` when Moonraker is down. |
| GET    | `/api/hardware`            | Flat free-text search over the raw component rows (`?q=`/`category`/`manufacturer`, paginated). The canonical, deduped, config-carrying entities have their own typed endpoints below. |
| GET    | `/api/hardware/categories` | The hardware categories + per-category **canonical** `counts` (raw kept as `rawCounts`) + total component count. |
| GET    | `/api/hardware/facets`     | Distinct values for the filter dropdowns — `boardClass` (boards), `nema` size (motors), `kind` (hosts), and `catalogSubsections` (per mixed catalog category → its sub-types). |
| GET    | `/api/hardware/manufacturers` | Canonical manufacturer entities (`?q`) — each with a stable `manufacturer_id`, auto-derived `aliases` and a `memberCount`, sorted most-connected first. |
| GET    | `/api/hardware/manufacturers/{manufacturer_id}` | One manufacturer's record (`?expand=related` adds its linked hardware, grouped by type). |
| GET    | `/api/hardware/mcus`       | Canonical MCU entities (`?q`/`family`) parsed from board `specs.MCU` (normalised to a canonical part) — each with `family`, `arch`, `boardCount`. |
| GET    | `/api/hardware/mcus/{mcu_id}` | One MCU's record (`?expand=related` adds the boards that use it). |
| GET    | `/api/hardware/boards`     | Canonical control-board entities (summaries; `?q`/`manufacturer`/`board_class`, paginated) — each board's connectors aggregated into one `ports[]`. |
| GET    | `/api/hardware/boards/{board_id}` | One board's full record (identity + specs + aggregated `ports[]` + detection `matchPatterns`; `?expand=related` adds links). |
| GET    | `/api/hardware/drivers`    | Canonical stepper-driver entities (summaries; `?q`/`manufacturer`/`klipper_only`, paginated) — one per chip, deduped. |
| GET    | `/api/hardware/drivers/{driver_id}` | One driver's full record (specs + Klipper support + copyable `[tmcXXXX]` config snippet; `?expand=related`). |
| GET    | `/api/hardware/motors`     | Canonical stepper-motor entities (summaries; `?q`/`manufacturer`/`nema`, paginated) — one per model, deduped. |
| GET    | `/api/hardware/motors/{motor_id}` | One motor's full record (specs + recommended `run_current` + current presets + copyable config snippet; `?expand=related`). |
| GET    | `/api/hardware/hosts`      | Canonical host-computer entities (summaries; `?q`/`manufacturer`/`kind`, paginated) — SBC / x86 / OS-image, deduped. |
| GET    | `/api/hardware/hosts/{host_id}` | One host's full record (specs + Klipper-open flag + copyable `[mcu host]` config snippet; `?expand=related`). |
| GET    | `/api/hardware/catalog`    | Canonical entities for one remaining category (`?category=…`, summaries; `?q`/`manufacturer`/`subsection`, paginated) — sensors / hotends / extruders / fans / displays / motion / nozzles / filament / electronics, deduped. `subsection` filters a mixed category by sub-type. |
| GET    | `/api/hardware/catalog/{catalog_id}` | One catalog entity's full record (specs + copyable Klipper config snippet; `?expand=related`). |
| GET    | `/api/hardware/{type}/{id}/related` | Cross-entity relationships for any node (`boards`/`drivers`/`motors`/`hosts`/`catalog`/`manufacturers`/`mcus`), grouped by relation (O(1) graph walk). |

The interactive `/docs` page is the always-current, authoritative list (the
firmware API has many routes beyond the summary above).

Curated Klipper reference datasets (StallGuard tuning, hotends, board/MCU patterns, macros) live
under `app/data/reference/` and are served read-only by `app/services/reference_data.py`.

The driver write endpoints return an `ApplyResponse` with an i18n **`{ code, params, message }`**
contract: `code` (+ `params`) is a stable key the UI translates (`motorDrivers.apply.*`), and
`message` is the English fallback. Passthrough errors (Moonraker failures, `field_policy` /
value-validation text) carry `code: null` — their raw English text is shown verbatim.

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
