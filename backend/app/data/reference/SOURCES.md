# Reference data — sources & attribution

These curated datasets are extracted from upstream **GPL-3.0** projects and re-used here under
GPL-3.0 (FilaMind Flow is also GPL-3.0). Values are reproduced faithfully from the cited sources.

| File | Source project | License | Extracted from |
|---|---|---|---|
| `stallguard_profiles.json` | [Fragmon/klipper_max_flow_test](https://github.com/Fragmon/klipper_max_flow_test) | GPL-3.0 | `tmc_flow_test.py` — the `TriggerProfile` base + per-driver (TMC5160/2240/2209) slip-detection constants and StallGuard field map |
| `hotend_table.json` | [Fragmon/klipper_max_flow_test](https://github.com/Fragmon/klipper_max_flow_test) | GPL-3.0 | `README.md` / `docs/ADVANCED.md` / `tmc_flow_test_macros.cfg` — hotend melt-zone, expected max-flow, test presets |
| `board_patterns.json` | [SartorialGrunt0/Klipper-Wire-Configurator](https://github.com/SartorialGrunt0/Klipper-Wire-Configurator) (KWC) | GPL-3.0 | `backend/services/board_detector.py` — `BOARD_PATTERNS` (34) + `MCU_PATTERNS` (15) |
| `macros.json` | [SartorialGrunt0/Klipper-Wire-Configurator](https://github.com/SartorialGrunt0/Klipper-Wire-Configurator) (KWC) | GPL-3.0 | `frontend/src/utils/macroDesigner.ts` — the 11 built-in calibration macro definitions |

> Counts reflect the actual upstream source (not the rounded figures in early planning notes):
> board patterns = 34 (not 44), built-in macros = 11 (not 12). Each file's `_meta` records its provenance.
