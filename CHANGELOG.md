# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.154.1] - 2026-06-08

### Changed

- Documentation wording and consistency pass (CHANGELOG / ROADMAP / README).

## [0.154.0] - 2026-06-08

### Added

- **Complete motor autotune dataset (hardware DB).** Expanded the numeric `autotune` block
  (`resistance_ohm`, `inductance_H`, `holding_torque_Nm`, `max_current_A`, `steps_per_rev`) from
  188 to **589 of the 671** canonical motors via a manufacturer-by-manufacturer datasheet pass
  across ~30 brands (Nanotec, Japan Servo / Nidec, Sanyo Denki, Phytron, Oriental Motor, Trinamic,
  Lin Engineering, MOONS', Leadshine, StepperOnline, Wantai, MotionKing, FAULHABER, LDO,
  MinebeaMitsumi, Applied Motion, Soyo, Creality and more). Only datasheet-verified values were
  recorded — **no fabrication**; the remaining ~82 entries are series/placeholder rows, multi-phase
  motors, or parts with no published phase resistance/inductance and are intentionally left blank.
  Step angle is now stored faithfully (1.8° → 200, 0.9° → 400, and large-step can-stack motors such
  as the FAULHABER AM2224 at 24 steps/rev). This is the data foundation for driving Motor Drivers
  autotune from the full hardware catalog.

### Fixed

- **Implausible holding-torque value corrected.** One motor carried a `107.7 N·m` holding torque
  (a clear unit/extraction error) from the curated motor database; restored to its true `0.59 N·m`
  in both the source catalog and the hardware DB. The autotune regression test now enforces
  physically-plausible ranges for every field to catch such errors.

### Changed

- Internal data housekeeping in the stepper-motor and driver reference catalogs.

## [0.153.0] - 2026-06-08

### Added

- **Motor autotune parameters on the hardware DB (toward Motor-Drivers convergence).** 188 of the
  671 canonical motors now carry a numeric `autotune` block — `resistance_ohm`, `inductance_H`,
  `holding_torque_Nm`, `max_current_A`, `steps_per_rev` — the datasheet parameters the Motor Drivers
  autotune / `motor_constants` recommender needs. Merged from the existing curated motor database
  (no fabrication). This is the data foundation that lets the Motor Drivers tab eventually drive
  autotune from the full hardware catalog; the remaining motors await a datasheet-enrichment pass.
  Exposed on the motor detail record; regression test added.

## [0.152.0] - 2026-06-08

### Added

- **`HardwarePicker` — a reusable, DB-backed "pick a part" control (DB-3d).** Generalises the
  Motor Drivers `MotorPicker` into a type-driven component: give it `type` (`boards` / `drivers` /
  `motors` / `hosts`) and it pages the full canonical catalog from `/api/hardware/*` into a
  typeahead `ComboSelect`, emitting both the chosen id (`v-model`) and the full entity summary
  (`@select`) so a host widget can auto-fill from it (e.g. pre-filling a motor's `run_current`).
  Any widget can now embed catalog-backed part selection. Localised; unit-tested.

## [0.151.0] - 2026-06-08

### Fixed

- **I2C temperature-sensor snippets (deferred Wave-5 follow-up).** The 6 I2C chip sensors that still
  shipped a generic ADC-thermistor placeholder now carry correct Klipper config — `sensor_type:
  BME280` / `HTU21D` / `LM75` with an `i2c_address` (and commented `i2c_mcu` / `i2c_bus`). Three
  also had a broken `name` (`sensor_type: BME280`, `I2C (SPI on some)`) restored to the real chip
  family. Regression test extended.

## [0.150.0] - 2026-06-08

### Added

- **Catalog sub-type facet — the mixed categories are now filterable like boards.** Several catalog
  categories lump different component types together (Fans, Power & Bed = fans / power supplies /
  heated beds / build surfaces; Electronics & Wiring = connectors / power electronics / endstops /
  wire / filament sensors; Cameras & Displays; Motion & Mechanical; Sensors & Probes; Hotends &
  Heaters; Nozzles). That classification already lived in each entity's `subsection`; it's now
  surfaced as a **sub-type dropdown** in the catalog panel (the catalog equivalent of a board's
  class), backed by `catalogSubsections` on `GET /api/hardware/facets` and a `subsection` filter on
  `GET /api/hardware/catalog`. Single-type categories (Extruders, Filament Materials) get no facet.
  Localised across all seven languages. Regression test added.

## [0.149.0] - 2026-06-08

### Fixed

- **Hardware DB data audit, Wave 6 — text hygiene.** Fixed the doubled-word artefact in two board
  aliases (`Creality Creality 4.2.2/4.2.7` → `Creality 4.2.x`). The broad audit confirmed the rest
  of the dataset is clean here: **zero** mojibake (U+FFFD) and no doubled words in any spec value or
  config body (the only other matches were inside config comments). Regression test added. Duplicate
  board/catalog entries were intentionally **not** merged — they're kept by request (variant siblings
  resolve via aliases), so dedup remains a separate, deliberate decision rather than an audit fix.

### Notes

- This completes the six-wave hardware-DB data-quality audit (v0.143.0 toolhead → v0.149.0).

## [0.148.0] - 2026-06-08

### Fixed

- **Hardware DB data audit, Wave 5 — config / snippet integrity.** Cleared **39** `configSource`
  fields that held a description instead of a URL (so nothing renders a broken link); fixed **3**
  board snippets whose Klipper section header had a parenthetical annotation inside the brackets
  (`[lis2dw (accelerometer)]` → `[lis2dw]  # accelerometer`); corrected **8** sensor snippets that
  shipped a generic ADC-thermistor template for SPI / internal sensors — the MAX6675 / MAX31855 /
  MAX31856 / MAX31865 thermocouple+RTD amplifiers now carry the right `sensor_type` + SPI pins (and
  RTD params), and the MCU/host internal sensors use `temperature_mcu` / `temperature_host`. Fixed 3
  stale `mediaStatus: none` flags on boards that do have media links. (The I2C sensor snippets —
  BME280/HTU21D/LM75, where exact `sensor_type` support and i2c addressing need care — were left for
  a focused pass rather than risk a wrong config.) Regression test added.

## [0.147.0] - 2026-06-08

### Fixed

- **Hardware DB data audit, Wave 4 — motor NEMA + step-angle normalisation.** **124** motors that
  had no NEMA size now show one, back-filled from the high-confidence frame code in their part number
  (`42STH…`/`17H…` → NEMA 17, `35BYGF…`/`36STH…` → NEMA 14, etc.); only 28 truly-unparseable rows
  remain sizeless. The `stepAngle` field, previously written three ways (`1.8°`, `1.8 deg`, bare
  `1.8`), is normalised to a single degree-sign encoding (137 rows). Conservative: ambiguous size
  inferences, free-text rated-current strings, and near-duplicate merging were left for later (a
  wrong size is worse than a blank one). Regression test added.

## [0.146.0] - 2026-06-07

### Fixed

- **Hardware DB data audit, Wave 3 — manufacturer-field junk.** Cleaned 71 entries whose
  `manufacturer` held a spec or junk value instead of a maker: bare AWG wire rows (`elec-10-55`)
  rebuilt to `10 AWG` + a `Max current (A)` spec; AC fan/bed rows folded their `300×300` dimension
  into the name; heater-cartridge / silicone-heater / build-plate / buck-module rows moved the real
  product out of `manufacturer` into `name`; StallGuard endstop descriptions, bare gauge numbers
  and em-dashes blanked; the Raspberry Pi Compute Modules' truncated `Compute` manufacturer fixed to
  `Raspberry Pi`; and the open-hardware community boards (RAMPS 1.4 / Melzi / CRAMPS) had their prose
  "manufacturer" blanked (no single maker). Conservative + scoped to genuine errors — valid short
  names (MK8, V6, a 608 bearing) and real manufacturers were left untouched. Regression test added.

## [0.145.0] - 2026-06-07

### Fixed

- **Hardware DB data audit, Wave 2 — board class taxonomy.** The `boardClass` enum was just
  `mainboard` / `toolhead` / `printer-preset`, so two kinds of non-controller board had no correct
  home and were lumped in as `mainboard`. Added two classes: **`expansion`** for the 7 Duet 3 CAN-FD
  expansion / external-driver boards (3HC, 1XD, 1HCL family — they daisy-chain off a mainboard, they
  aren't standalone controllers), and **`host`** for the 10 host SBCs / SoCs / carriers that were
  mis-filed in `boards[]` (CB1, CB2, MKS Pi, Nebula/Sonic/Speeder pads, the K1 host pad, the Pi
  carriers) so they no longer masquerade as selectable main controllers. Both new classes get a
  localised filter label and appear in the Boards "class" facet. (Retagged rather than removed — three
  carry real GPIO port data and the lossless-aggregation invariant must hold.) Regression test added.

## [0.144.0] - 2026-06-07

### Fixed

- **Hardware DB data audit, Wave 1 — catalog product identity restored.** A broad read-only audit
  found catalog rows where the real product had been swapped into the `manufacturer` column while
  `name` held only a generic word or a bare spec. Recovered **80** rows: thermocouple/sensor chips
  shown as `SPI`/`I2C` → `MAX6675` / `MAX31865` / `HTU21D` …; power connectors shown as `Connectors`
  → `XT30` / `XT60` / `XT90` …; heater cartridges shown as `12 V`/`24 V` → `Ceramic cartridge 12 V
  30 W (6×20)` …; nozzles shown as a thread `M6 × 1.0` → `E3D V6` / `MK8` … (the thread moved to a
  spec); and 7 linear-rail rows all mislabelled `EGH25CA / EGW25CA` renamed to their real family
  (`MGW7/9/12/15`). A regression test locks it. (The audit's larger raw counts were over-stated —
  generic material/mechanical types like `PLA` or a `T8` leadscrew correctly have no manufacturer
  and were left untouched.)

## [0.143.0] - 2026-06-07

### Fixed

- **Hardware DB data audit — toolhead boards were mis-classified.** Most toolhead boards
  (BigTreeTech EBB36/EBB42 and EBB-SB, SB2209 / SB2240 / SB2040, Mellow Fly-SHT / Fly-SB2040,
  LDO Nitehawk / Orbitool O2, MKS/LDO THR36/THR42, FYSETC SB CAN, Caramba, the K1 nozzle
  sub-board, …) were tagged `mainboard` instead of `toolhead` — the catalog showed only 10
  toolheads when there are 55. Reclassified the 45 affected boards from a curated set of
  toolhead families plus each board's own `Class` / `Form factor` / `Role` spec signal (the
  Duet 1HCL closed-loop high-current CAN *expansion* boards are intentionally kept out of the
  toolhead class). A regression test now locks the classification. The dataset gained a
  `_meta.version`, which also refreshes the read cache so the fix is visible immediately.

## [0.142.0] - 2026-06-07

### Added

- **Hardware Browser faceted filters (DB-3c).** Each catalog panel now exposes the filters the
  backend already supported, via the shared `EntityCatalog` facet slot: **Boards** filter by class
  (mainboard / toolhead / printer-preset), **Motors** by NEMA size, **Hosts** by type
  (SBC / x86 / OS / locked), and every panel (boards / drivers / motors / hosts / catalog) by
  **manufacturer**. A new `GET /api/hardware/facets` returns the distinct filter values (board class,
  normalised NEMA size, host kind); the dropdown options are fetched once and shared across panels.
  Localised across all seven languages.

## [0.141.0] - 2026-06-07

### Changed

- **Hardware Browser internal refactor (DB-3b) — shared `EntityCatalog` component, no behaviour
  change.** The five near-clone detail panels (Boards / Drivers / Motors / Hosts / Catalog) each
  repeated the same shell — search box, result list, pagination, per-row expand with a detail cache,
  copy-config helper, loading / error states and cross-link deep-link focus. That shell is now one
  shared `EntityCatalog.vue`; each panel is a thin wrapper that supplies a `fetchPage` / `fetchDetail`
  closure and renders only its own bespoke summary + detail markup via slots. Behaviour and layout
  are unchanged (verified by an old-vs-new parity review); the panels shed ~55 % of their code and
  new entity catalogs / faceted filters (DB-3c) now plug into one place.

## [0.140.0] - 2026-06-07

### Added

- **Hardware Browser cross-links + brand / MCU browsing (DB-3a) — the linking graph is now
  visible and navigable.** Building on the DB-2 backbone, the browser surfaces the relationships
  in the UI:
  - **Cross-link chips** on every expanded entity (board / driver / motor / host / catalog) — its
    manufacturer, MCU(s) and on-board / supported drivers shown as clickable chips. Click one to
    **jump straight to that entity** (the right tab opens and the target is expanded).
  - **Two new browse tabs** — **Brands** (the canonical manufacturers, each with its part count and
    its linked hardware) and **MCUs** (the chips parsed from board specs, each with the boards that
    use it). Start from a brand or a chip and see everything that uses it.
  - An illustrated **"Linked hardware"** help topic + glossary entry explain the feature.
  - Localised across all seven languages.

## [0.139.0] - 2026-06-07

### Added

- **Hardware-DB linking backbone (DB-2) — the reference DB is now a connected graph.** The data's
  relationships used to be islands (free-text `manufacturer`, the MCU buried in a board's specs,
  driver compatibility hidden in a spec string). DB-2 turns them into a precomputed, in-memory
  cross-entity graph (built once at load) with O(1) lookups:
  - **Canonical manufacturers** — every directory entry gets a stable `manufacturer_id`, auto-derived
    aliases (parenthetical acronyms, `/`-separated co-brands) and a `memberCount`; variant spellings
    collapse (`BTT` / `BigTreeTech` / `BIGTREETECH (BTT)` → one id), recurring real brands missing
    from the directory are derived, and "no single maker" placeholders (generic / clone / RepRap) are
    excluded so they never become misleading link hubs.
  - **MCU as a first-class entity** — board `specs.MCU` strings are parsed with a whitelist of
    chip-family rules and normalised to a canonical part (`STM32F407VET6` → `stm32f407`), so package
    fragments, host SoCs and noise never become phantom MCUs.
  - **Edges** use composite keys (`<type>:<id>`, since ids are not unique across types) linking each
    entity to its manufacturer, each board to its MCU(s), and each board to its on-board / supported
    drivers.
  - New read-only endpoints: `GET /api/hardware/manufacturers` (now canonical) + `/manufacturers/{id}`,
    `GET /api/hardware/mcus` + `/mcus/{id}`, a generic `GET /api/hardware/{type}/{id}/related`, and
    `?expand=related` on the entity detail routes (fetch an entity and its neighbours in one call).
  - A CI edge-validator test guarantees the graph has no dangling edges and every referenced
    manufacturer / MCU resolves.

## [0.138.0] - 2026-06-07

### Changed

- **Hardware-DB performance foundation (DB-1) — invisible speedups, zero behaviour change.**
  `reference_data` now builds its entity lists, **`id→entity` index dicts**, and a **precomputed
  per-item search haystack** once at load (no more per-request rebuilds / per-call re-filtering):
  every `*_by_id` lookup is O(1), and the flat `/api/hardware` free-text search no longer rebuilds
  3.8k lowercased strings on each query (~16× faster on a Pi). The precomputed haystacks are kept in
  a parallel list (not on the entities) so nothing leaks into API responses.
- **Cache-Control + ETag on the immutable `/api/hardware/*` reads** (weak ETag derived from the
  dataset version/sizes; `304 Not Modified` on a match) — card-expand detail re-fetches become free
  over the wire, and the browser serves repeats from cache. Busts automatically on redeploy.

### Fixed

- **Catalog tile counts now show the canonical entity count** (e.g. boards 380, not the raw 1357
  rows) so a category tile matches what its panel lists. `GET /api/hardware/categories` `counts` are
  now canonical (boards / drivers / motors / hosts / the 9 catalog categories); the raw row counts
  remain available as `rawCounts`.

## [0.137.0] - 2026-06-07

### Docs

- **Professional documentation refresh + the Hardware-DB backbone plan.** Updated the main
  **README** (the status callout now reflects all **nine** shipped widgets, not three; the Hardware
  Browser is described as the canonical, config-carrying database it has become; the stale bottom
  "Roadmap" — which listed already-shipped widgets as *planned* — was rewritten). **ARCHITECTURE.md**
  gained a "Hardware database (`/api/hardware/*`)" section and its widget / i18n-catalog lists were
  brought current. **backend/README** flat-search row clarified. **ROADMAP** gained a new
  **"Hardware DB — cross-widget data backbone"** phased plan (DB-1 performance foundation →
  DB-2 linking/`links` layer + `/related` API → DB-3 shared `EntityCatalog` + `HardwarePicker` +
  facets/cross-links → DB-4 media + silo convergence; SQLite+FTS5 documented as the only-if-triggered
  storage end-state). No code changes.

## [0.136.0] - 2026-06-07

### Added

- **Missing-manufacturer sweep across the catalog categories — +79 branded entities, 22 new makers
  (catalog 1,224 → 1,303).** Hotends: **Phaetus** (Dragon/Dragonfly/Rapido/Rapido 2), **Slice
  Engineering** (Mosquito/Copperhead), **Trianglelab**. Extruders: **Orbiter** (v1.5/v2), **Bondtech
  LGX/LGX-Lite**, **LDO Galileo/Galileo 2**, **Voron Clockwork CW1/CW2** (gear ratios from the
  official config), **Vz-HextrudORT**, **BIQU H2**, **Sprite Pro**. Fans: **Noctua / Sunon / Delta /
  GDStime / Winsinn / Sanyo San Ace** + PSUs **Mean Well** (LRS/RSP/UHP/HRP). Probes/sensors:
  **Voron TAP, BTT Eddy, Mellow FLY Eddy, Duet Smart Effector, E3D PZ, Annex Quickdraw, BIQU
  MicroProbe, PINDA 2, Omron/inductive, HX711 load-cell**. Motion: **Gates** belts, **HIWIN /
  Misumi / THK** rails (with dynamic/static load ratings), **igus** DryLin, **Ooznest / OpenBuilds /
  RobotDigg** pulleys & screws. Each gets the same copyable config snippet. Datasheet-verbatim;
  non-real products (Vipfix, Decapod, Panda Hands) were correctly rejected.

### Fixed

- Motor `nema` display normalised (strip a leading "NEMA") so cards show "NEMA 17" not "NEMA NEMA17".

## [0.135.0] - 2026-06-07

### Added

- **Deep OEM motor-series coverage — +82 part numbers (589 → 671 canonical motors).** Expanded the
  Nidec Servo / Japan Servo **KH** family (KH42HM2/JM2/KM2 -801/-851/-901/-951 windings, the
  KH42xx-B900 series KH4234/4238/4242/4248/4254-B901xx/B951xx, KH56 NEMA-23 B900, KH39 NEMA-16) and
  the Sanyo Denki **103** series (103H52 NEMA-17, 103H67 NEMA-20, 103H712 NEMA-23, 103H782 NEMA-24,
  103H822 NEMA-34, plus classic 103-xxx STEP-SYN), all from authoritative datasheets. Includes the
  three exact OEM motors a user photographed: `KH4248-B90008`, `KH42KM2R001C`, and Sanyo
  `103-594-0611`. Sanyo Denki now 51 models, Japan Servo / Nidec 58. Each gets the recommended
  `run_current` + copyable config snippet; specs omitted (not guessed) where a datasheet didn't confirm them.

## [0.134.0] - 2026-06-07

### Added

- **Every remaining catalog category now gets the canonical-entity + copyable-config treatment.**
  The 9 still-flat categories — Sensors & Probes, Hotends & Heaters, Extruders, Fans/Power/Bed,
  Cameras & Displays, Motion & Mechanical, Nozzles, Filament Materials, Electronics & Wiring —
  are deduped into **1,224 canonical entities**, each with a **copyable Klipper config snippet**
  (real config where it applies — `[adxl345]`/`[probe]` for sensors, `[extruder] gear_ratio` for
  extruders, `lcd_type:` for displays, `rotation_distance` for leadscrews/belts, `sensor_type`/
  `max_temp` for hotends, filament temp presets — or an honest note otherwise). Reads each row's
  existing `Klipper` spec hint where present; fixed a source-data column swap in Filament / Cameras
  & Displays / Motion (product was in the manufacturer field).
- Backend: generic `GET /api/hardware/catalog?category=…` (summaries, paginated) +
  `GET /api/hardware/catalog/{catalog_id}` (full record incl. snippet). Frontend: a generic
  `CatalogPanel.vue` — clicking any category tile opens a rich deduped view with the copy section
  (no extra top-level tabs; the tab bar stays at 6). New `test_catalog_entities.py`.

## [0.133.0] - 2026-06-07

### Added

- **Missing global stepper-motor manufacturers — 12 new makers, 55 new motors (534 → 589 canonical).**
  Added Japan Servo / Nidec Servo (incl. the exact `KH42KM2R015A` NEMA-17 OEM motor + the KH42/56/
  39/60/86 + KV28 families), Minebea / MinebeaMitsumi / Astrosyn, Applied Motion Products, Sonceboz,
  Tamagawa Seiki, Rtelligent, Fulling Motor, McLennan, Nippon Pulse, and Phidgets — all from
  authoritative datasheets (rated current / R / L / holding torque / frame), each getting the same
  recommended `run_current` + copyable config snippet as the rest of the motor catalog. The 11 new
  vendors are added to the manufacturer directory (274 → 285). Per-axis community current presets
  were preserved intact.

## [0.132.0] - 2026-06-07

### Added

- **Host-computer catalog with copyable Klipper host config — a dedicated Hosts tab in the Hardware
  Browser.** The 222 `Host Computers` rows become **220 canonical host entities** (185 SBCs, 22 x86
  hosts, 12 Klipper OS images, 1 locked/proprietary), each with unified specs (SoC / CPU / RAM /
  storage / suggested Klipper OS) and a **copyable config snippet**: the 208 open Linux hosts emit
  the `[mcu host]` Linux-process-MCU block (`serial: /tmp/klipper_host_mcu`) + a setup note (runs
  the Klipper host stack; flash the printer MCU separately; suggested OS image); OS-image rows and
  locked/proprietary hosts (Bambu) get an honest note instead — no `[mcu host]` block.
- Backend: `GET /api/hardware/hosts` (summaries, `?q`/`manufacturer`/`kind`, paginated) +
  `GET /api/hardware/hosts/{host_id}` (full record incl. snippet). Frontend: `HostsPanel.vue` on a
  new **Hosts** tab (the "Host Computers" catalog tile opens it). i18n ×7. New `test_host_catalog.py`
  locks entities, snippet coverage, and the open-host-block-vs-note distinction.

## [0.131.0] - 2026-06-07

### Added

- **Stepper-motor catalog with a recommended `run_current` + copyable config — a dedicated Motors
  tab in the Hardware Browser.** The 577 `Stepper Motors` rows become **534 canonical motor
  entities** (43 community slug-rows merged into their marketing twin). Each motor carries unified
  specs (NEMA / step angle / rated current / holding torque / R / L), a **recommended Klipper
  `run_current`** (~0.7 × rated phase current, RMS — present on 526) and a **copyable config
  snippet** (`[tmc2209 stepper_x] run_current: …` + a `full_steps_per_rotation`/`microsteps`/
  `rotation_distance` skeleton). Where community per-axis current presets exist they're attached
  and shown in the snippet.
- Backend: `GET /api/hardware/motors` (summaries, `?q`/`manufacturer`/`nema`, paginated) +
  `GET /api/hardware/motors/{motor_id}` (full record incl. snippet + presets). Frontend:
  `MotorsPanel.vue` on a new **Motors** tab (the "Stepper Motors" catalog tile opens it). i18n ×7.
  New `test_motor_catalog.py` locks entities, snippet coverage, and the run_current recommendation.

## [0.130.0] - 2026-06-07

### Added

- **Stepper-driver catalog with copyable Klipper config — a dedicated Drivers tab in the Hardware
  Browser.** The 84 flat `Stepper Drivers` rows are deduped into **55 canonical driver entities**
  (one per chip), each with unified specs, manufacturer, interface, Klipper-support flag, and a
  **copyable config snippet**: the 14 Klipper-managed TMC chips emit a ready `[tmcXXXX stepper_*]`
  block (run_current / sense_resistor / stealthchop_threshold / interpolate, UART or SPI per chip);
  the 41 standalone step/dir and closed-loop parts (A4988, DRV8825, TB6600, LV8729, L6470, MKS
  Servo…) get an honest note (current set by Vref pot / runs its own firmware — no `[tmc]` section).
- Backend: `GET /api/hardware/drivers` (summaries, `?q`/`manufacturer`/`klipper_only`, paginated) +
  `GET /api/hardware/drivers/{driver_id}` (full record incl. snippet). Frontend: `DriversPanel.vue`
  (mirrors BoardsPanel) on a new **Drivers** tab; the "Stepper Drivers" catalog tile opens it.
  i18n in all 7 locales. New `test_driver_catalog.py` locks dedup, snippet coverage, and the
  TMC-section-vs-standalone-note distinction.

## [0.129.0] - 2026-06-07

### Changed

- **Deduplicated same-product board entities — 408 → 380 boards** (272 standalone + 108 printer
  presets). 28 redundant entries (created when the same physical board appeared in multiple source
  files, e.g. `creality-v4.2.7`/`creality-4-2-7`/`4-2-7`, `skr-v1-4`/`skr-1-4`/`skr-v1-4-2`, the
  `duet-3-mainboard-6hc`/`-6hc-2` pairs) were merged into one canonical each. **Lossless merge, not
  a delete:** all data is unioned into the canonical, every removed `board_id`/model name is folded
  into the canonical's `aliases` (so search and detection still resolve them), `matchPatterns` are
  unioned, and `xlsx_source_rows.portRowCount` is summed (the lossless CI lock still holds).
  Genuine form-factor/driver variants are kept separate (EBB36 ≠ EBB42, SB2209 ≠ SB2240). Also
  tidied a few canonical display names (collapsed a doubled "Creality Creality" source artifact).

## [0.128.0] - 2026-06-07

### Added

- **Copyable pin-map (`configSnippet`) on every board — all 408 now have the copy section.** Was
  188/408; the 220 standalone control boards that lacked one now have it. **366 carry a real,
  verbatim Klipper pin map** copied from authoritative sources (Klipper repo `generic-*.cfg` +
  official vendor GitHub Klipper sample configs — BigTreeTech, Mellow, MKS, FYSETC, Duet3D,
  Creality, Anycubic, LDO, Qidi, etc.), with a `configSource` link. For those boards the `ports[]`
  table was also upgraded from connector-level to real Klipper pins (the connector data is preserved
  under `connectors`).
- **42 boards carry an honest note instead of fabricated pins** where no published Klipper pin map
  exists: 11 host SBCs (CB1/CB2, Raspberry Pi, Sonic/Nebula/Speeder pads, MKS Pi…), and 31 boards
  that are USB-CAN bridges (U2C, UTC), ESP32/HC32 parts needing a community Klipper port (FYSETC E4,
  some Anycubic Trigorilla / Creality HC32 revisions), closed-loop servo modules (MKS SERVO42/57),
  or Duet 3 CAN expansion boards (1HCL/1XD/3HC) that have no standalone pin map.
- Bounded Agent-tool method (6 waves, strict verbatim-only / anti-fabrication). Agents flagged real
  source facts, e.g. FYSETC Catalyst = STM32H723 (not F401), SB CAN Toolhead = STM32F072, and that
  "Mellow Eagle" / GD32F303 Trigorilla Gen V4 have no published Klipper pin map.

## [0.127.1] - 2026-06-07

### Fixed

- **Printer-preset `boardHint` quality.** 23 presets had a terse `boardHint` extracted from the
  Klipper config header (e.g. `"Anet"`, `"ZNP Robin"`, `"Tronxy"`, and one malformed sentence
  fragment `"HC32F460. The"`); the never-overwrite enrichment merge had kept these stubs instead of
  the richer web-researched values. Upgraded 17 of them to the fuller value (e.g. Anet A8 →
  `"Anet V1.0 (Melzi clone, ATmega1284P)"`; Neptune 3 Pro → `"ZNP Robin Nano DW V2.2 (STM32F401)"`;
  Ender-2 Pro HC32 → `"Creality Ender-2 Pro 32-bit V2.4 (HDSC HC32F460 MCU, MS35775_HC32F460KETA)"`).
  Kept the 6 where the config-derived value is more specific or version-distinct (e.g. CR-6 SE 2020
  `"early 4.5.2"`, Ender-3 Pro `"32-bit Creality 4.2.2"`, RatRig V-Minion's config-authoritative
  `"Octopus Pro v1.1"`).

## [0.127.0] - 2026-06-07

### Added

- **Printer-model preset enrichment — all 108 presets. The entire hardware database is now
  enriched: 406 web-enriched + 2 hardware-verified = every one of the 408 board entities.** The
  printer presets already carried Klipper pin-maps; this adds printer-level data: stock control
  board (`boardHint`, set on 106/108), kinematics, build volume, bed, hotend, stock extruder,
  temps, year, and stock driver type, plus config-affecting electronics notes and Klipper-relevant
  config notes. Same bounded Agent-tool method (4 waves). **+1046 specs, +107 media links, +266
  electronics facts, +266 config notes.** Covers Anet, Anycubic, Artillery, BIQU, Creality (full
  Ender/CR line), Elegoo, Eryone, FLSUN, Geeetech, Kingroon, Longer, LulzBot, MakerGear, Monoprice,
  Prusa MINI+, RatRig, SeeMeCNC, Sovol, Sunlu, TEVO, Tronxy, Two Trees, Velleman, Voxelab, Wanhao,
  FlashForge and more.
- Agents corrected/clarified many stock-board facts from authoritative sources: Ender-2 Pro HC32
  variant ships an HDSC HC32F460 (needs a community Klipper port, not STM32 firmware); Ender-3 Max
  mixes TMC2208 (X/Y) with A4988 (Z/E); LulzBot Mini 2 = Einsy RAMBo (TMC2130 SPI), TAZ 6 = full
  RAMBo (A4982); Monoprice Mini Delta = Malyan STM32F070 (has an official Klipper config); Wanhao
  Duplicator 6 reads a PT100 via an onboard amplifier (not a 100k thermistor); Wanhao i3 v2.1 =
  Melzi ATmega1284P; Anycubic Vyper / Sovol SV06 = GD32F103 (verify chip before flashing).

## [0.126.0] - 2026-06-07

### Added

- **Web enrichment waves 8 + 9 + 10 — the final 75 boards. Board enrichment is now complete:
  every one of the 300 standalone control boards in the database is web-enriched** (the remaining
  108 entries are printer-model pin-map presets, a separate category). Same bounded Agent-tool
  method (4 agents/wave writing results to files; no runaway). **+462 specs, +164 media links,
  +224 electronics facts, +225 config notes.** Covers the long tail: Qidi Q1 Pro / X-Plus 3 /
  X-Max 3, Sovol SV07, Raspberry Pi host, the legacy Klipper-generic boards (Alligator R2/R3,
  Azteeg X5 Mini, Cramps, RADDS, Re-ARM, RuRAMPS, Archim, Megatronics, Minitronics, Mini-RAMBo,
  Printrboard G2, RemRam, Mightyboard, GT2560, Ultimaker UltiMainboard), the BigTreeTech SKR
  legacy/E3 line (CR6, E3 DIP, E3 Turbo, Mini E3 v1.0, Mini MZ, v1.1, E3 RRF), Creality 4.2.7 /
  4.2.10, FYSETC Cheetah v1.1 / F6 / S6 v2, Mellow Fly CDY/Gemini/Super Infinity HV/Flyboard,
  TH3D EZBoard Lite / V2.0, Duet DueX expansion, and ERCF EASY BRD.
- Agents corrected several MCU/vendor facts from authoritative sources: SKR E3 Turbo = LPC1769
  (not STM32F407); TH3D EZBoard Lite V1.2 = LPC1769 (not STM32F103); Terminator 3 = Sunlu
  GD32F303 (not FLSUN); ERCF EASY BRD = Seeeduino XIAO SAMD21; Mellow Super Infinity HV = STM32F407;
  Flyboard = Mellow FLYF407ZG; Printrboard G2 = Atmel SAM3X8C; RemRam = STM32F765 (no "v4" exists);
  Alligator = RepRap/Alligator project (not UltiMachine); `simulavr` flagged as the Klipper AVR
  simulator target, not physical hardware.

## [0.125.0] - 2026-06-07

### Added

- **Web enrichment waves 6 + 7 — 64 more boards (now 223 web-enriched).** Bounded 4-agent method,
  agents write results to files directly. +274 specs, +102 media links, +197 electronics facts, +181
  config notes. Covers the full Duet 2/3 line + 1LC/1HCL/1XD/3HC toolheads & expansions, classic AVR
  boards (RAMPS 1.4, Melzi, Megatronics, MKS Gen, Azteeg X3), Smoothieboard, Replicape, Prusa
  Einsy/Buddy/Archim, Mellow Fly (Super8/Gemini/E3/SHT-36/SHT-42/Ruby/Caramba/MMB/Eagle/UTC/Roto),
  MKS (Gen/SGEN/Robin/Monster8/SKIPR/SERVO42B/SERVO57C/THR), Creality (4.2.x/K1/Sonic Pad/Nebula
  Pad/SV06 lineage), Artillery Ruby. Agents corrected many facts from source (1LC = Duet3D not BTT;
  Roto = STM32F042 USB; Ruby v1.2 = Artillery STM32F401; UTC = STM32G0B0; SHT-36 V2 = GD32F103).

## [0.124.0] - 2026-06-07

### Added

- **Web enrichment wave 5 — 32 more boards (now 159 web-enriched).** Same bounded 4-agent method;
  agents now write their results to files directly (no manual transcription). +68 specs, +32 media,
  +96 electronics facts, +96 config notes. Covers the BigTreeTech SKR (1.3/1.4/2/3/Pico/Mini-E3) +
  Octopus + Manta (M4P/M5P/M8P/E3EZ) + Kraken + GTR + EBB/SB toolheads, FYSETC Spider/S6/Cheetah/
  Catalyst.K/E4, Mellow Leviathan, LDO Nitehawk-36, Duet 2. Agents corrected several MCU facts from
  source (Cheetah v1.2 = STM32F103, v2.0 = STM32F401, FYSETC E4 = ESP32).

## [0.123.0] - 2026-06-07

### Added

- **Web-researched enrichment for 32 more boards (wave 4).** Same bounded 4-agent method (clean, no
  runaway). Now **127 boards web-enriched** total (129 with config-affecting electronics).
  - **+190 specs, +62 media links, +103 electronics facts, +96 config notes.**
  - Covers the BigTreeTech EBB42 CAN family (v1.0–v1.2 + GEN2), SB2209/SB2240 toolheads (RP2040 &
    STM32 & TMC2240), Manta M8P, the full SKR line (v1.3 / v1.4 / v1.4 Turbo / SKR 3 / SKR 3 EZ in
    H743 & H723 / SKRat / Mini E3 v2.0), U2C v2.1, Creality CR-FDM-V2.4.S4 / Ender-3 V3 SE / K1 host
    pad / K2 Plus, and the Raspberry Pi host.
  - Config-critical facts: *EBB42 V1.0 CAN on PB8/PB9 @250k vs G0B1 PB0/PB1 @1M (firmware not
    interchangeable)*, *SKR 3 / 3 EZ ship in H743 and H723 builds (different Klipper target)*,
    *Creality GD32F303 boards build as STM32F103 28KiB*, *K1 host = Genic X200 SoC + a separate
    GD32F303 motion MCU*.

## [0.122.0] - 2026-06-07

### Added

- **Web-researched enrichment for 32 more boards (wave 3).** Same bounded 4-agent method (clean, no
  runaway). Now **95 boards web-enriched** total.
  - **+153 specs, +48 media links, +99 electronics facts, +96 config notes.**
  - Covers RAMPS 1.6, Sanguinololu, the **Anycubic Trigorilla family** (8/16/32-bit, HC32F460 /
    GD32F303 / STM32F103 / GD32F103 across i3-Mega, Kobra, Vyper), **ZNP K1 = Elegoo Neptune 4**
    (STM32F402 + RK3328), ZNP Robin Nano DW, MKS THR36/42 + SGEN_L V2, BTT Octopus V1.0 / SKR V1.4
    Turbo / U2C v1.x & v2.x / EBB36 v1.0–v1.2 & GEN2, FYSETC Spider v2.2/v3.0-F446 / S6 v2, Hurakan.
  - Config-critical facts: *EBB36 hotend pin PA2 (v1.0/v1.1) → PB13 (v1.2)*, *EBB GEN2 uses LIS2DW
    not ADXL345*, *Anycubic boards use soldered GC6609/TMC clones — manual run_current, no sensorless*,
    *ZNP K1 stock MCU firmware is non-standard — a plain Klipper .bin won't work*.

## [0.121.0] - 2026-06-07

### Added

- **Web-researched enrichment for 31 more boards (wave 2).** Same bounded method (4 research agents,
  fixed batches — clean, no runaway). Now **63 boards web-enriched** total.
  - **+122 specs, +50 media links, +101 electronics facts, +93 config notes** from manufacturer /
    OSH-repo / wiki / Klipper-config sources.
  - Covers Creality 4.2.2 / 4.2.7 / 4.2.10 / Ender-3 V3 SE, Prusa Buddy & xBuddy, the full Duet 3
    family (6HC / 6XD / 3HC / 1HCL / 1XD + SBC mode), BigTreeTech EBB36/42 CAN v1.0–v1.2 & GEN2
    toolheads, Mellow Fly-SB2240, MKS Monster8 / Robin / SGEN_L, Azteeg X5, Archim.
  - Config-critical facts captured, e.g. *Creality 4.2.2 driver-letter codes (A=2208/B=2209/H=2225)*,
    *EBB V1.2 hotend pin moved PA2→PB13*, *EBB toolheads use a 2.2 kΩ thermistor pull-up*,
    *Fly-SB2240 = onboard TMC2240 + LIS2DW*, *Ender-3 V3 SE = GD32F303 + MS35774 (no UART tuning)*.

## [0.120.0] - 2026-06-07

### Added

- **Web-researched enrichment for 32 boards (wave 1).** Using 4 bounded research agents (each given
  a fixed batch — no runaway), enriched 32 popular boards that had no Klipper config, from
  authoritative manufacturer / OSH-repo / wiki sources:
  - **+107 confirmed specs**, **+57 media links** (product/repo/wiki/pinout/schematic/datasheet),
    **+100 config-affecting electronics facts**, **+96 Klipper config notes**.
  - The electronics are the high-value part — e.g. *LDO Nitehawk-SB uses a 2.2 kΩ thermistor pull-up
    → set `pullup_resistor: 2200`*; *Octopus Pro per-driver 60 V MOTOR_POWER vs 28 V jumper*;
    *Manta M8P V2 PT1000 pull-up jumper*; *Spider v3 permanent 120 Ω CAN termination*; *Duet 2 =
    SPI TMC2660, current set in firmware*. All shown in the board detail (electronics + config notes
    + links), traceable to source.
  - Covers BigTreeTech, FYSETC, LDO, Duet3D, Mellow, MKS, Creality boards (incl. CB1/CB2/MKS-Pi SBCs,
    U2C bridge, EBB/Nitehawk/SB2040 toolheads).

## [0.119.0] - 2026-06-07

### Added

- **Printer-preset pin maps from Klipper's 108 official `printer-*.cfg` configs.** Finishes the
  local authoritative data pass: each sample printer config is parsed into a **`printer-preset`**
  board record (printer model + board hint from the header + MCU + the real pin map as structured
  ports + a copy-ready config snippet + `configSource` URL). Great for owners of a specific machine
  (Creality, Anet, Anycubic, Sovol, Voron kits, …) — search your printer, get the exact pins.
  - **+108 printer-preset boards → 408 total** (290 mainboards · 108 printer-presets · 10 toolheads).
  - Coverage: **188 boards with a full copy-ready pin map**, **384 with a known MCU**.
  - All deterministic + traceable (no guessing). Next: bounded web-agent waves to enrich the boards
    that have no Klipper config (specs/electronics/media).

## [0.118.0] - 2026-06-07

### Added

- **Real pin maps for the remaining boards, from Klipper's official board configs.** Parsed all
  **84 `generic-*` board configs** from `Klipper3d/klipper/config/` (authoritative, deterministic
  parse — no guessing) and folded them into the catalog:
  - **49 existing boards enriched** with their real Klipper pin map (every section's pins as a
    structured port: signal/role + `invert`/`pull-up` flags + the Klipper config key + a usage hint),
    the **MCU** from the config header, and a **copy-ready config snippet**; the prior connector
    aggregation is preserved under `connectors`.
  - **35 new boards added** that weren't in the catalog before → **300 boards total**.
  - Each carries `configSource` (the exact Klipper file URL) — every datum is traceable.
  - Coverage now: **80 boards with a full copy-ready pin map**, **277 with a known MCU**.

## [0.117.0] - 2026-06-07

### Added

- **Board data made *usable*, not just viewable.** Every board port now carries a **usage hint +
  the Klipper config key** it feeds (added to **all 265 boards / ~960 ports**), so you know exactly
  where each connector goes in `printer.cfg`.
- **SV08 built to full reference depth** (mainboard + toolhead):
  - A **structured pin map** per port — each pin with its signal/role, the Klipper key, and
    `invert` (`!`) / `pull-up` (`^`) flags + a per-pin hint.
  - An **Electronics** block of config-affecting facts (e.g. *bed is mains-AC via SSR — PA0 is a
    3.3V trigger, never wire mains*; *PT1000 on the default 4700Ω pull-up*; *sensorless homing via
    diag pins*; 3.3V logic).
  - **Config notes** + a **copy-ready config snippet** of the verified pin map.
- The Hardware Browser's board detail renders all of this: a "Use it" column on the ports table,
  the electronics list, config notes, and a one-click **Copy** config snippet. New i18n keys ×7.

## [0.116.0] - 2026-06-07

### Added

- **Sovol SV08 fully ingested — the printer under test, mapped from its own config (gold proof).**
  The SV08 was missing from the board catalog entirely (it existed only as a "Host Computers" row).
  It is now two complete, hardware-verified board records:
  - **`sovol-sv08` (mainboard)** — STM32F103xE, CoreXY quad-gantry, **6 integrated TMC2209** (X, Y,
    Z1–Z4), with **14 ports** carrying their real Klipper pins (every stepper's step/dir/enable/uart/
    diag, heated bed, exhaust/controller/MCU fans, filament sensor, RGB, LED, EXP display).
  - **`sovol-sv08-toolhead`** — STM32F103xE, 1× TMC2209 extruder, hotend + PT1000, probe, part &
    hotend fans, onboard ADXL345 — **6 ports** with real pins.
  - Every pin verified against the unit's own `printer.cfg`; media links to the Sovol3d/SV08 repo +
    mainboard pin-definition PDFs + product page. New `test_sv08_fully_ingested` locks it in.

## [0.115.0] - 2026-06-07

### Added

- **Hardware Browser → "Boards" tab — the enriched board catalog is now visible.** The aggregated
  `boards[]` entity (263 boards with their aggregated `ports[]`, specs, and reference media) was
  reachable only via the API and the Board-Topology card (which stays empty when detection is
  chip-only, e.g. the SV08). A new **Boards** tab lists every board with a search box; each card
  shows the manufacturer, class, port count and a ports-by-category summary, and **expands** to the
  full spec sheet, the **reference links** (pinout / schematic / repo / product / datasheet), and a
  **ports table** (connector / function / pins). The catalog's "MCU & Boards" tile now opens this
  view instead of the raw flat rows.
  - New `BoardsPanel.vue` + `fetchBoards`/`fetchBoardDetail`; new Boards-tab i18n keys ×7 locales.

## [0.114.0] - 2026-06-07

### Added

- **Board enrichment + reference media links (Phases 5+6 of the DB overhaul).** Researched the most
  common boards and folded the results into the catalog: **58 boards gained +458 confirmed spec
  fields** (MCU / arch / voltage rails / driver slots / USB / CAN / bootloader offset / dimensions …)
  + **23 inferred manufacturers**, each from an authoritative manufacturer / open-source-hardware
  source.
- **Per-board media is exposed as a `media` block** (product page, OSH repo, wiki, image, pinout,
  schematic, datasheet) — **link-only** (verified `http(s)` URLs to the manufacturer's own source),
  not re-hosted binaries, to respect asset licensing and keep the repo lean. The Board Topology
  board card now renders these as a row of **reference links** (i18n labels ×7 locales).
- CI: media URLs are validated as real `http(s)` links (never fabricated/relative paths).

## [0.113.0] - 2026-06-06

### Added

- **Hardware Browser — sectioned catalog + "Search all" (Phase 9 of the DB overhaul, item 9).**
  The browser now opens on a **Catalog** view: a tile per category with a hand-drawn illustration,
  the category name, and a **live item count**, plus a prominent **"Search all"** tile. Clicking a
  tile drops into the **Search** view pre-filtered to that category. The two views are a persistent
  `WidgetTabs` strip (state preserved across switches).
  - New `CategoryIllo.vue` (13 Neo-Brutalist category glyphs) + `GET /api/hardware/categories` now
    returns **per-category counts**.
  - New catalog/tab i18n keys across all 7 locales.

## [0.112.0] - 2026-06-06

### Added

- **Board Topology → catalog link (Phase 8 of the DB overhaul).** Each detected MCU now resolves a
  catalog **`board_id`** by matching its connection signature against the boards' folded
  `matchPatterns` (with a normalized-name fallback). When a board is identified, the topology card
  shows a **"View board details"** button that lazy-loads `GET /api/hardware/boards/{board_id}` and
  shows the aggregated `ports[]` summary + spec sheet inline.
  - Surfaced as a **suggested** match the user can ignore — a serial/canbus id usually reveals only
    the chip, so `board_id` is `null` rather than a false guess (locked by tests).
  - New board-detail i18n keys across all 7 locales.

## [0.111.0] - 2026-06-06

### Fixed

- **Max-Flow hotend table — fixed the key mismatch + expanded 8 → 96 (Phase 7 of the DB overhaul).**
  The widget read `expected_max_flow_mm3s` / `suggested_temp_c` but the data shipped
  `expected_flow_mm3s` and no temp — so the flow hint and the temp/max auto-fill **never fired**.
  - Standardised every row on `expected_max_flow_mm3s` (kept `expected_flow_mm3s` as an alias);
    added `suggested_temp_c` to the curated rows so the auto-fill works.
  - **Generated 88 more hotends** from the big-DB `Hotends` sub-category (96 total), with a careful
    flow normaliser that excludes print-speed (`mm/s`), converts `mm³/min`, takes the range max, and
    drops nozzle-size leaks → 68/96 with a parsed flow, the rest `null` (unpublished, never guessed).
    Each generated row carries `max_temp_c` and a derived test `preset` where the flow is known.
  - Regression test locks the contract (every row has `expected_max_flow_mm3s`; curated rows keep a
    `suggested_temp_c`).

## [0.110.0] - 2026-06-06

### Added

- **Canonical board entities — connectors aggregated into `ports[]` (Phase 2-4 of the DB overhaul).**
  Fixes the structural "duplication" where each control board was repeated once per pin/connector
  (963 flat rows for ~116 boards). The board data is now a proper `boards[]` entity — **263 boards**
  (116 with aggregated ports, 147 spec-only), all **963 connector rows aggregated losslessly** into
  per-board `ports[]` (a `count`-sum proof guarantees no row is dropped). Each port carries a
  controlled `category` (motor / heater-bed / heater-hotend / thermistor / fan / power / endstop /
  probe / can / usb / …), connector style, pins, pitch and MPN (real MPNs kept, "not published"
  placeholders → `null`). Each board has a stable `board_id` slug, inferred manufacturer, a join to
  its spec row (`MCU`/`Arch`/`Drivers`/…; 87 joined), and detection `matchPatterns` folded in.
  - Purely **additive** — the flat `items[]` are untouched (the Hardware Browser keeps working);
    the new entity is exposed at **`GET /api/hardware/boards`** (summaries) and
    **`GET /api/hardware/boards/{board_id}`** (full record with `ports[]`).
  - This is the foundation the next phases build on (enrichment, media, Board-Topology link, the
    sectioned Browser).

## [0.109.0] - 2026-06-06

### Fixed

- **Restored hardware data the v0.108.0 clean had wrongly dropped (Phase 1 of the DB overhaul).**
  The previous "data-quality clean" over-reached and removed real products. This restores them and
  hardens the gates so it cannot recur:
  - **Restored 577 stepper-motor products** (the whole "Stepper motors" section, e.g. ACT Motor,
    Creality, FUYU, LDO …) that had collapsed from 669 → 64. Stepper Motors is back to **641**.
  - **Restored 20 wiring/endstop reference rows** (wire-ampacity guidance + endstop/switch types)
    dropped from Electronics & Wiring (176 → **195**), with names derived from their own specs.
  - The manufacturer **directory stays in `manufacturers[]`** (274) instead of polluting the product
    list — no directory data lost.
  - **Tightened the dataset to its technical reference values** and added a CI guard to keep it that way.
  - New CI regression: **per-category floors** (`test_no_category_was_gutted`) so a future regen can
    never silently gut a whole category again.
  - Curated DB total: **3,643 components** / 274 manufacturers / 13 categories.

## [0.108.0] - 2026-06-06

### Fixed

- **Hardware DB data quality (from the post-sprint audit).** Fixed the column-misrouting that
  left **318 items unnamed**: identity-header name selection + a spec-derived fallback → **0 empty
  names**; **dropped 605 manufacturer-directory rows** that were polluting the product list (they
  belong to the 274-row manufacturer directory, not the components); de-duplicated exact records.
  The curated DB is now **3,047 clean components / 274 manufacturers / 13 categories**.
  - New **CI data-quality gates** (`test_hardware.py`): empty-name = 0, no exact-duplicate records,
    no manufacturer-directory leakage; plus a **cross-source consistency test** locking each TMC
    StallGuard field across `driver_catalog` / `stallguard_profiles` / `field_policy`.
  - Known follow-up: ~35 % of item manufacturer strings still sit outside the directory (deeper
    per-category column reconciliation) + optional cross-ref keys to the motor/driver catalogs.

## [0.107.0] - 2026-06-06

### Changed

- **Max-Flow safety hardening (from the post-sprint audit).** Before any live run can read garbage:
  - **Chopper-mode / StallGuard preflight** — `run_max_flow` now refuses a driver with no StallGuard,
    a missing `[<driver> extruder]` section, or the wrong chopper mode (SG4 needs StealthChop, SG2
    needs SpreadCycle); returns 422 with an actionable message instead of measuring noise.
  - **SG4 bias-region floor** — StallGuard samples below `SG_MIN_INFORMATIVE` (50 for tmc2209/tmc2240)
    are dropped, so the 2209's low bias-region readings aren't analyzed as real load.
  - **Safe-extrusion floor raised to 180 °C** (was 150) to avoid reading cold-extrusion grind as slip.
  - Locked the tmc2240 StallGuard field (`sg4_thrs`) consistent across driver_catalog / stallguard_profiles
    with a test. +8 backend tests.

## [0.106.0] - 2026-06-06

### Added

- **Macro Designer — macro variable substitution (Track A, completes A2).** The G-code simulator
  now renders Klipper-macro `{ ... }` value expressions before simulating: `{ params.X }`,
  `{ params.X | default(N) }`, bare `{ NAME }`, and simple `int` / `float` / `upper` / `lower`
  filters. `POST /api/macro/simulate` accepts an optional `params` map; unresolved expressions are
  left intact and warned, and `{% … %}` control flow is reported (not evaluated — full Jinja is
  future work). Dependency-free `macro_render.py`; +10 backend tests.

## [0.105.0] - 2026-06-06

### Added

- **Config Templates library (Track A — completes A4).** A curated set of ready-to-paste Klipper
  config blocks and macros baked into the backend (`templates.json`): start/end sequences,
  pause/resume/cancel, filament load/unload, M600, `[input_shaper]`, `[bed_mesh]`,
  `[firmware_retraction]`, `[exclude_object]`, and more.
  - `GET /api/reference/templates` + `reference_data.templates()`.
  - A new **Config Templates** widget: category filter + cards (name, category, description,
    required sections, the template body) with a one-click copy (works on a plain-http LAN host).
  - New `configTemplates` namespace + sidebar label across all 7 locales; +3 backend tests.

## [0.104.0] - 2026-06-06

### Added

- **Hardware Browser — widget UI (Track A).** A new widget on `/api/hardware`: a search box +
  manufacturer field + category filter (`ComboSelect`), paginated result cards each showing the
  component's manufacturer, name, category badge, and full spec sheet. Match count + "showing
  X–Y of N" + Prev/Next paging. New `hardwareBrowser` namespace + sidebar label across all 7
  locales. +4 frontend tests. The insertable config/macro template library follows.

## [0.103.0] - 2026-06-06

### Added

- **Hardware Browser — data + search backend (Track A).** A curated 3D-printing hardware
  reference baked into the backend (`hardware.json`: **3,671 components** across 13 categories +
  a **274-manufacturer** directory), with a pure search service and read-only endpoints:
  - `GET /api/hardware` — free-text (`?q=`) + `category` + `manufacturer` filters, paginated
    (server-capped page size).
  - `GET /api/hardware/categories` and `GET /api/hardware/manufacturers`.
  - +8 backend tests (incl. a dataset-integrity check). The browser UI + a template library follow.

## [0.102.0] - 2026-06-06

### Added

- **Macro Designer — editor UI (Track A).** A new widget on `POST /api/macro/simulate`: a G-code
  editor (with a sample + clear), a **Simulate** button, and the results — a **2D toolhead path**
  drawn as SVG (solid = extrusion, dashed = travel, theme-aware, flipped-Y), stat badges
  (moves / travel / extrusion / time estimate), the bounding box, a collapsible per-command
  timeline, and any warnings. Plus a **built-in macro reference library** (from `/api/reference/macros`)
  with each macro's description + required sections and an "Insert into editor" action. New
  `macroDesigner` namespace + sidebar label across all 7 locales. +4 frontend tests.

## [0.101.0] - 2026-06-06

### Added

- **Macro Designer — G-code simulator core (Track A).** `gcode_sim.py` + `POST /api/macro/simulate`:
  parses a literal G-code program (`G0`/`G1` moves, `G90`/`G91`, `M82`/`M83`, `G92`, `G28`) and
  returns the toolhead path (2D), bounding box, total travel + extrusion, a rough time estimate,
  and a per-command timeline. Inline comments stripped; unsupported commands recorded as warnings.
  Pure compute, no printer. +10 backend tests. The editor UI and Jinja / macro expansion follow.

## [0.100.0] - 2026-06-06

### Added

- **Board Topology — widget UI (Track A).** A new read-only widget on `GET /api/topology`: the
  host (SBC) node above a grid of MCU cards, each showing its connection type (USB / CAN bus /
  UART, colour + label coded), chip, a best-effort board guess with match confidence, and its
  identifier. Refresh, loading / unreachable / empty states, and an illustrated help drawer.
  New `boardTopology` namespace + sidebar label across all 7 locales. This completes A3.

## [0.99.0] - 2026-06-06

### Added

- **Board Topology — detection backend (Track A).** `board_topology.py` + `GET /api/topology`:
  reads the live `configfile` sections and builds a host → MCU topology — each MCU's connection
  type (CAN bus / USB / UART), its identifier, and a best-effort chip / board guess from the
  reference pattern tables. Read-only; returns `reachable=false` when Moonraker is down.
  +9 backend tests. The topology-graph UI and a pin-conflict validator follow.

## [0.98.0] - 2026-06-06

### Added

- **Max-Flow — measurement loop + widget (Track B).**
  - `POST /api/maxflow/run` (actuating): heats the hotend, ramps the extrusion flow while
    sampling the extruder's TMC StallGuard load, and feeds each step to the `max_flow` analysis
    core. **Safe by construction** — refused while the printer is busy (409); the heater is
    **always turned off in a `finally`**; and the ramp **stops at the first detected slip** so no
    filament is ground past it. `MoonrakerClient.upload_file` was added earlier; this adds the
    extruder StallGuard sampling. +4 backend tests (clean run, slip + early-stop, busy-refused,
    heater-off-on-error).
  - New **Max-Flow widget**: pick a hotend (prefills temp + flow range), preview the exact ramp
    (flow → feedrate per step + total filament), then run behind a **safety checklist + confirm
    gate**. Shows the max sustained flow, slip point, and suggested slicer values (80 % / 90 %),
    with an illustrated help drawer. Fully internationalized across all 7 locales.
  - Note: the live StallGuard field for a TMC2209 extruder during extrusion is best-effort and
    validated on first live run (`sg_samples_seen` flags when none was read).

## [0.97.0] - 2026-06-06

### Added

- **Max-Flow — planner foundation (Track B).** `max_flow_service.py` (pure, hardware-free):
  - `flow_to_feedrate` (mm³/s → extruder mm/min for a given filament) + `plan_ramp` (the
    ascending flow steps a run would execute) + `recommend` (conservative 80 % / 90 % slicer
    values from a measured max) + `hotend_hint` (match the reference melt-zone table) +
    safety-bounded `validate`.
  - `POST /api/maxflow/plan` — a dry-run preview: every flow step's feedrate + filament pushed,
    the driver's StallGuard field, and totals. **Pure compute, no actuation.**
  - +16 backend tests. The gated measurement loop (heat → extrude → sample StallGuard) and the
    live run land in a later slice.

## [0.96.0] - 2026-06-06

### Added

- **Config Editor — gated save path (Track A).** The Raw view is now editable, with a
  confirm-gated write back to the printer:
  - `POST /api/config/save` — backs the current file up to `filamind-backups/<name>.<ts>.bak`
    first, then overwrites it. **Refused while the printer is busy** (printing / paused / error → 409).
  - `POST /api/config/restart` — triggers `FIRMWARE_RESTART` to apply a saved change (also
    refused while busy).
  - UI: edit the raw text → **Save** opens a confirm panel ("I understand this writes to the
    printer") → on success it shows the backup path and offers a one-click **Restart firmware**
    (its own confirm). A "● Unsaved changes" indicator + Revert. Path-traversal guarded.
  - `MoonrakerClient.upload_file` / `firmware_restart` helpers; new `configEditor.edit/save/restart`
    i18n keys across all 7 locales; +10 backend tests.

## [0.95.0] - 2026-06-06

### Added

- **Config Editor — viewer UI (Track A).** A new widget that reads the live config through the
  `/api/config/*` routes and presents it:
  - A file picker (`ComboSelect`) over every `.cfg` / `.conf` file on the printer, defaulting to
    `printer.cfg`.
  - Collapsible `[section]` cards → a parameter table (key / value + inline comment, multi-line
    values intact), the `SAVE_CONFIG` block flagged, with expand/collapse-all.
  - A validation banner that surfaces structural issues (e.g. a duplicate section) — colour- **and**
    label-coded (Error / Warning), not colour alone.
  - Structured and raw views (`WidgetTabs`), section/parameter counts, and an illustrated
    `HelpDrawer` (topics + glossary + how-to steps).
  - Fully internationalized across all 7 locales; new `configEditor` namespace + sidebar label.
  - Read-only; the guided, confirm-gated save path follows.

## [0.94.0] - 2026-06-06

### Added

- **Config Editor — read path (Track A keystone).** Backend endpoints that read the live
  Klipper config through the round-trip `klipper_config` engine:
  - `GET /api/config/files` — list the editable config files (`.cfg` / `.conf`) under
    Moonraker's `config` root.
  - `GET /api/config/file?filename=` — parse one file into a structured view: sections →
    params (key / value / separator / inline comment, multi-line values preserved), the
    `SAVE_CONFIG` block flagged, plus light validation issues. Read-only; a path-traversal
    guard restricts reads to the config root.
  - New `config_service.py` and two `MoonrakerClient` file helpers (`list_files`,
    `get_file_text`); +14 backend tests. The viewer UI and the gated save path follow.

## [0.93.1] - 2026-06-06

### Changed

- Editorial: documentation and in-code wording pass (README / ROADMAP / ARCHITECTURE and a
  few Motor Drivers help blurbs). No behavioral change; `dist` rebuilt.

## [0.93.0] - 2026-06-06

### Added

- **Phase 0.2 (foundation) — config engine + flow-analysis core.** Two internal backend modules
  the upcoming widgets build on (pure logic; no Moonraker, no motion):
  - `klipper_config.py` — a round-trip Klipper INI engine (`parse` / `dump` / `validate`): preserves
    comments, `:`/`=` separators, section order, multi-line values and the auto-saved `SAVE_CONFIG`
    block, so `dump(parse(x)) == x`. Light validation (duplicate sections, empty names, stray params).
    Backs the planned Config Editor.
  - `max_flow.py` — a pure StallGuard slip-detection analysis core: per-step median / IQR / CV stats +
    CV-spike / IQR-spread / run-outlier detectors driven by the per-driver reference constants; turns a
    flow sweep's samples into a max-flow result. Backs the planned Max-Flow widget.
  - +23 backend tests (12 config round-trip/validate + 11 flow-analysis).

## [0.92.1] - 2026-06-06

### Changed

- Reference-dataset `_meta` and the surrounding docs simplified to concise internal descriptions.

## [0.92.0] - 2026-06-06

### Added

- **Phase 0 (foundation) — reference-data layer.** First build step of the planned expansion: a
  backend module that serves curated Klipper reference datasets the upcoming widgets reuse.
  Baked under `backend/app/data/reference/` and exposed read-only:
  - `GET /api/reference/stallguard` + `/stallguard/{driver}` — per-driver StallGuard slip-detection
    tuning constants (base + overrides; `{driver}` returns the merged effective set + the SG field).
  - `GET /api/reference/hotends` — hotend melt-zone / expected max-flow / test presets (8 classes).
  - `GET /api/reference/boards` — board (34) + MCU (15) identification patterns.
  - `GET /api/reference/macros` — 11 built-in calibration macro definitions.
  - Pure static reads (no Moonraker / writes / gating); payloads returned verbatim. +4 backend tests.

### Docs

- **Roadmap expanded with a planned widget/data program.** Documented a phased plan extending
  FilaMind across the full Klipper tuning + configuration surface: a shared **Phase 0 foundation**
  (reference-data layer + a config engine), then two parallel tracks — **Config Editor · Macro
  Designer · Board Topology · Hardware Browser + Templates** and **Max-Flow · Motor-Drivers
  auto-SGT/slip-detection + Sensorless wizard**. See [ROADMAP.md](ROADMAP.md) + README.

## [0.91.1] - 2026-06-06

### Fixed

- **Sidebar now themes (was stuck bright yellow in dark themes).** The app sidebar hardcoded
  `bg-brand-yellow`, so it stayed loud yellow in Neon/Dark/High-Contrast and clashed with the dark
  content. Added a dedicated `--c-sidebar` token (yellow in Light — the signature look — and a dark
  rail in the other themes) and pointed the sidebar at it. (Caught by live browser verification.)

## [0.91.0] - 2026-06-06

### Added

- **Theme system — 4 themes with a header switcher (Neon default).** The whole look is now driven by
  CSS custom properties, so a single switch restyles the entire app. Ships **Neon** (deep indigo/violet
  with a soft glow + rounded corners — the new default), **Dark** (neutral charcoal), **Light** (the
  original warm Neo-Brutalist look), and **High Contrast** (near-black/white for accessibility).
  - **How it works:** every design token (the 9 colors + the shadow/radius style tokens) is a CSS
    variable; the Tailwind tokens reference them (`rgb(var(--c-*) / <alpha-value>)`, `var(--nb-*)`), so
    **every existing utility** (`bg-paper`, `border-ink`, `bg-brand-cyan`, `shadow-brutal`, `rounded-brutal`)
    recolors per theme with no component changes. Adding a theme = one `[data-theme]` block + a registry entry.
  - **No-flash:** an inline `<head>` script applies the saved theme before first paint. Choice persists
    (`localStorage`), and is exposed via a header **theme selector** (translated in all 7 locales).
  - **Charts follow the theme:** the Input Shaping SVG charts/heatmaps no longer hardcode hex — they use
    the token variables, so they recolor correctly in dark/neon/contrast.
  - Built by a specialized multi-agent workflow (spec → tokens+CSS / runtime+switcher / chart-decouple →
    adversarial review), then verified live in the browser across all four themes.

## [0.90.0] - 2026-06-06

### Changed

- **Density & legibility pass (all widgets) — bigger text, clean card borders.** The dense data UI
  used `text-[10px]`/`text-[9px]` throughout and **dashed** borders on every collapsible sub-panel,
  which read as cramped and unfinished. Bumped the type one step across the three widgets + shared UI
  (`text-[9px]`→`10px`, `text-[10px]`→`11px`; existing 11px kept), so the new hierarchy is 14 / 12 /
  11 / 10 px. Replaced every **dashed** sub-panel/divider border with a **solid** one, so panels read
  as clean cards. No layout, copy, or behaviour change — purely visual legibility. Completes the UX
  series (help reorg + this).

## [0.89.0] - 2026-06-06

### Changed

- **Help reorganised across Input Shaping + Firmware Manager (same kit as Motor Drivers).** Applied
  the v0.88.0 help pattern to the other two widgets so the whole app is consistent:
  - **Named contextual hints** — every inline `HelpNote` in Input Shaping and the Firmware Manager
    now shows its **topic title** as the trigger instead of a generic "what's this?".
  - **One Guide drawer per widget** — a single **"❓ Guide"** button (in each widget's header,
    reachable from every tab) opens the shared `HelpDrawer`: Input Shaping's gathers every topic +
    glossary; the Firmware Manager's also includes the build→flash "how to read" steps.
  - **Removed the scattered link rows** — the Firmware Status tab's 7-link help dump + its steps
    toggle are gone (now in the drawer), and Input Shaping's stray standalone glossary link is gone
    (the co-located, now-named hints per view remain).
  - Adds `{inputShaping,firmware}.help.{guide,guideTitle,close[,howToRead]}` across all 7 locales
    (879 keys/locale). This completes the help-reorg phase of the UX series; a density/legibility
    pass (font size + replacing dashed borders with clean cards) is next.

## [0.88.1] - 2026-06-06

### Fixed

- **Guide drawer — "how to read" steps rendered as raw message objects.** `HelpDrawer` resolved its
  ordered steps with `tm(stepsKey)` over a **dynamic** key and rendered each item directly, which
  shows vue-i18n's raw compiled message nodes (`{t,b,s,i…}`) instead of text. Resolve each item with
  `rt()` so the steps render as readable text. (Caught by live browser verification on the printer.)

## [0.88.0] - 2026-06-06

### Changed

- **Help reorganised — named hints + one Guide drawer (Motor Drivers).** The help layer was
  scattered and undiscoverable: every hint was an identical generic "what's this?" link, and the
  Motor Drivers widget ended in a row of **13 indistinguishable** such links (plus two more at the
  top). You couldn't tell what any of them revealed without clicking each. Now:
  - **Named contextual hints** — each inline `HelpNote` shows its **topic title** as the trigger
    (e.g. "Run / hold current") instead of a generic "what's this?", so hints are distinguishable at
    a glance.
  - **One Guide drawer** — a new shared `components/ui/HelpDrawer.vue` (off-canvas, RTL-aware,
    closes on backdrop/✕/Esc) gathers the whole help layer in one organised place: the "how to read"
    steps, every topic (title + illustration + body), and the glossary. A single **"❓ Guide"** button
    in the widget header opens it.
  - **Removed the scattered link rows** — the 13-link bottom dump and the duplicate top links are
    gone (their content now lives in the drawer + the co-located named hints).
  - Adds `motorDrivers.help.{guide,guideTitle,close,howToRead}` across all 7 locales (872 keys/locale).

  This is the first of a short series; the same pattern will be applied to Input Shaping and the
  Firmware Manager, followed by a density/legibility pass.

## [0.87.0] - 2026-06-06

### Changed

- **Motor Drivers — register editor reorganised (layout only).** The advanced register editor was a
  single flat, `flex-wrap` list of ~20 registers with no alignment — controls, ranges, live values and
  the per-field **Set** buttons packed left and wrapped independently, so nothing lined up (it read as
  a scattered wall). It is now split into **labelled sections** (Chopper · StealthChop (PWM) ·
  StallGuard · Thresholds & timing · CoolStep · Other) that mirror the backend `field_policy` catalog
  groups, each laid out as an **aligned CSS-grid** (name · control · range/live-value · Set) so every
  column lines up and the Set buttons form a single right-hand column. **Every control and button is
  unchanged** — same fields, same gated write paths, same per-field confirms; this is purely
  layout/organisation. Section headers are fully translated across the 7 locales. Also unified the
  collapsible sub-panel toggles across the widget (Register editor / Recommend / Live monitor /
  Homing) into consistent full-width section headers (chevron + icon + bold label). No behaviour
  change.

## [0.86.0] - 2026-06-06

### Changed

- **i18n Phase 4 complete (backend message codes) — the i18n epic is done.** The Motor Drivers write
  path (`drivers_apply.py`) now tags every user-facing result with an i18n `code` + `params` alongside
  its English `message`: the `ApplyResponse` schema gained `code: str | None` and `params: dict`, and
  each structured result (nothing-to-apply, busy-refusals, applied / re-initialized / autotuned /
  field-set / CoolStep / homed / motors-synced) carries a stable `motorDrivers.apply.*` code with its
  interpolation args. The frontend renders these through a new `applyResultText(res)` helper
  (`t('motorDrivers.apply.' + res.code, res.params)`, falling back to `res.message`), wired into the
  five panels that surface a write result (Recommend, RegisterEditor, Sensorless, Homing, MotorSync) —
  so apply/revert/home/sync toasts now follow the selected language. **Passthrough errors stay English
  by design** (Moonraker failures, `field_policy` / value-validation text carry no `code` — they are
  technical upstream strings). Added the 18 `motorDrivers.apply.*` keys (English source + the six
  translations) so `i18n:keydiff` parity holds (863 keys/locale). The English values are byte-identical
  to the backend `message`, so the fallback is exact. **No g-code or behavior changed.**

## [0.85.0] - 2026-06-06

### Changed

- **Arabic RTL layout polish.** With Arabic selected (`<html dir=rtl>`), the Neo-Brutalist UI now lays
  out correctly right-to-left:
  - **Logical-property sweep** — migrated the directional Tailwind utilities to their logical
    equivalents across the components (`ml-/mr-`→`ms-/me-`, `pl-/pr-`→`ps-/pe-`,
    `text-left/right`→`text-start/end`, the sidebar's `border-r`→`border-e` and the mobile drawer's
    `left-0`→`start-0`), so margins, padding, text alignment, and the sidebar/drawer flip with `dir`.
  - **Arabic font stack** — IBM Plex Sans Arabic / Noto Sans Arabic, applied via `:lang(ar)` to the
    prose + display faces (data stays in JetBrains Mono); loaded with a system fallback like the Latin
    faces. (Self-hosting for fully-offline hosts remains the existing roadmap item.)
  - **Brutalist tweaks that don't translate** — under `:lang(ar)`, `uppercase` and `letter-spacing`
    are dropped (Arabic has no case and tracking breaks its cursive joining); the bold weight keeps the
    "shout". The hard offset shadow stays put (a fixed light source, not a reading-direction cue) while
    the button press-translate is mirrored.

  Bidi-isolation of inline measurements and self-hosted Arabic webfonts are minor follow-ups.

## [0.84.0] - 2026-06-06

### Added

- **Six languages — the UI is now multilingual.** Added full translations for **Arabic, German,
  Simplified Chinese, French, Spanish, and Russian** — every one of the 845 catalog keys, across all
  five namespaces (`common` / `shell` / `firmware` / `input-shaping` / `motor-drivers`). A
  **language switcher** now appears in the header (it was hidden while only English shipped); picking
  a language lazy-loads its catalog and updates `<html lang>` / `dir` (Arabic switches the document to
  RTL). Each translation keeps brand / protocol / register / G-code tokens and SI unit symbols in
  Latin, preserves every `{placeholder}` and emoji, and uses the correct **per-locale plural rules**
  (registered for Arabic = 6 forms, Russian = 3, Chinese = 1; en/de/es/fr = 2). Adding a language was
  exactly "drop in a `src/locales/<code>/` folder" — no component changed. CI `i18n:keydiff` now
  enforces that every locale carries the exact `en` key set.

  *Arabic note:* the document flips to RTL automatically; the Neo-Brutalist **RTL layout polish**
  (logical-property sweep, Arabic webfonts, bidi-isolated measurements) lands in a follow-up.

## [0.83.0] - 2026-06-06

### Changed

- **i18n Phase 2 complete (Firmware Manager — templates).** Externalized all of the Firmware Manager
  widget's template strings — `FirmwareUpgradeWidget.vue` (tabs, the build→flash steps, status /
  services / devices / batch actions, confirm copy, errors) and the panels `FirmwareGuided`,
  `FirmwareFlashConfirm`, `FirmwareConfigEditor`, `FirmwareDevicesPanel`, `ExternalFirmwarePanel` —
  into the `vue-i18n` catalog (`firmware.{widget,guided,flashConfirm,configEditor,devices,external}.*`;
  **845 `en` keys**). Real counts use **vue-i18n pipe plurals** (e.g. `{n} setup issue | {n} setup
  issues`, edits badge, "Restored N profile(s)"); the `STEPS` guide moved to the catalog (`tm()`);
  tab / batch arrays became `computed`; inline markup uses `<i18n-t>`; units / tokens stay literal.
  Build-log lines (`>>> compiling…`) are kept English as technical console output. **No visible
  change.** New mount + pipe-plural test suite. **This completes i18n Phase 2** — all three widgets
  (Input Shaping, Motor Drivers, Firmware Manager) and the app shell are now fully localizable.

## [0.82.0] - 2026-06-06

### Changed

- **i18n Phase 2 (Firmware Manager — help layer).** Externalized the Firmware Manager widget's help
  copy (10 `HelpNote` topics + a 6-term glossary) into the `vue-i18n` catalog (`firmware.help.*`;
  **652 `en` keys**), mirroring the shipped Input Shaping / Motor Drivers pattern: `help.ts` is now
  structural (`HELP_TOPICS` / `HELP_ILLO` / `GLOSSARY_KEYS`; the `STEPS` build→flash guide stays for
  the templates slice), and `HelpNote.vue` renders through `t()`. `compare.ts` needed no change (it
  holds only status codes / data, no user-facing prose). **No visible change.** New `help.spec.ts`
  mount test guards the rendering. The Firmware templates (the orchestrator + panels) follow next.

## [0.81.0] - 2026-06-05

### Changed

- **i18n Phase 2 (Motor Drivers — templates; widget complete).** Externalized all of the Motor
  Drivers widget's template strings — `MotorDriversWidget.vue` (intro, tabs, the "how to read this"
  steps, card labels, states) and every panel (`LiveMonitor`, `RecommendPanel`, `MotorSyncPanel`,
  `SensorlessPanel`, `HomingPanel`, `GuidedWizard`, `MotorPicker`, `RegisterEditor`) into the
  `vue-i18n` catalog (`motorDrivers.{widget,liveMonitor,recommendPanel,motorSync,sensorless,homing,
  guidedWizard,motorPicker,registerEditor}.*`; **619 `en` keys**). The `STEPS` const moved from
  `help.ts` into the catalog (rendered via `tm()`); sentences with inline markup use `<i18n-t>`; tab
  arrays became `computed`; units / tokens stay literal. **No visible change.** A new mount-test
  suite renders every panel and the orchestrator, guarding against leaked keys. **With this, the
  entire Motor Drivers widget is localizable** — only the Firmware Manager widget remains for Phase 2.

## [0.80.0] - 2026-06-05

### Changed

- **i18n Phase 2 begins (Motor Drivers — help layer + format helpers).** Externalized the Motor
  Drivers widget's help copy (17 `HelpNote` topics + a 9-term glossary) and the `format.ts` display
  helpers (current / chopper / health / temperature / homing-method / StallGuard-range hints / motor
  spec line / fault flags / recommendation labels) into the `vue-i18n` catalog
  (`motorDrivers.{help,format}.*`; **510 `en` keys**), mirroring the shipped Input Shaping pattern:
  `help.ts` is now structural (`HELP_TOPICS` / `HELP_ILLO` / `GLOSSARY_KEYS`; the `STEPS` const stays
  for now), `HelpNote.vue` renders through `t()`, and `format.ts` uses the global translator (option
  A — no signature changes, so `format.spec.ts`'s 44 assertions pass unchanged). **No visible
  change.** New `help.spec.ts` mount test guards the rendering. The Motor Drivers templates follow
  next.

## [0.79.0] - 2026-06-05

### Changed

- **i18n Phase 1 complete (Input Shaping — templates).** Externalized the Input Shaping widget's own
  template strings — `InputShapingWidget.vue` (tabs, intro, result / chart labels, the cfg block,
  the audit view) and the sub-panels `ResonanceFromPrinter.vue`, `VibrationsProfile.vue`,
  `ResonanceCompare.vue`, `CsvSourceChooser.vue` — into the `vue-i18n` catalog
  (`inputShaping.{widget,fromPrinter,vibrationsView,compareView,csvSource}.*`; **423 `en` keys**).
  Sentences with inline markup use `<i18n-t>` (keeping their `<code>` / `<strong>` tags); the
  tab-label arrays became `computed`; units / tokens stay literal. **No visible change.** New mount
  tests render every Input Shaping panel and guard that no raw key path leaks. **This completes i18n
  Phase 1** — the app shell and the entire Input Shaping widget are now fully localizable.

## [0.78.0] - 2026-06-05

### Changed

- **i18n Phase 1 (Input Shaping — guided wizard + audit).** Externalized the last two prose helpers
  and the Guided wizard UI. **`guided.ts`** keeps only the step *structure* (id / motion / manual);
  the step labels / titles / why-text move to `inputShaping.guided.steps.<id>`, and the gate
  headlines resolve through `t()`. **`audit.ts`** routes its per-property record labels, verdicts,
  and value formats through `inputShaping.audit.*`. **`GuidedTune.vue`** is now fully localized — it
  reads the step text via `t()` and its own chrome (buttons, the motion-confirm, the summary) comes
  from the catalog (the summary's inline `printer.cfg` uses `<i18n-t>` to keep the `<code>` tag). A
  new **mount test** guards that the wizard renders from the catalog with no raw keys leaking.
  **No visible change** (English identical; 244 `en` keys; 135 tests). With this, all of Input
  Shaping's display helpers are externalized — the widget's own template strings follow next.

## [0.77.0] - 2026-06-05

### Changed

- **i18n Phase 1 (Input Shaping — prose helpers).** Externalized the user-facing copy returned by
  five pure display helpers — `grade.ts` (A–F verdicts + factor labels/notes), `diagnose.ts`
  (mechanical-diagnostic cards), `compare.ts` (A⇄B metric rows + belt verdict), `recommend.ts`
  (next-step suggestions), and `axesMap.ts` (the axes-map verdict) — into the `vue-i18n` catalog
  under `inputShaping.*` (159 `en` keys now). Each helper resolves its strings through the global
  translator, so function signatures, call sites, and unit tests are unchanged. **No visible
  change** — English renders identically, numeric values keep their exact formatting, and units /
  tokens (Hz, %, ×, `max_accel`, `TEST_RESONANCES`, …) stay literal. `guided.ts` (its `STEPS`
  template coupling) and `audit.ts` (persisted records) follow in later slices.

## [0.76.0] - 2026-06-05

### Changed

- **i18n Phase 1 (Input Shaping — help layer).** Externalized the Input Shaping widget's help copy
  (the 14 `HelpNote` topics + the 6-term glossary) into the `vue-i18n` catalog. `help.ts` is now
  pure structure (topic order, per-topic illustration, glossary key order); the translatable text
  lives under `inputShaping.help.*` and `HelpNote.vue` renders it through `t()`. **No visible
  change.** The help test now asserts the catalog keys, and a new **component-mount test** verifies
  `HelpNote` renders its title/body/glossary through i18n (the first mounted-component i18n test).

## [0.75.0] - 2026-06-05

### Changed

- **i18n Phase 1 (shell).** Externalized the app chrome into the `vue-i18n` catalogs — the first
  slice of the string migration. The sidebar (nav, brand tagline, footer), header (Mainsail link +
  nav toggle), the connection-status badge, the empty-home copy, the per-widget **nav titles /
  descriptions**, and the shared `describeError` backend-unreachable message now render through
  `t()`. A small `widgetTitle` / `widgetDescription` helper prefers a `shell.widgets.<id>` key and
  falls back to the widget's registered English, so a widget without a catalog entry still shows a
  sane label. **No visible change** — English renders identically and the language switcher stays
  hidden until a second locale ships in a later phase.

## [0.74.0] - 2026-06-05

### Added

- **Internationalization (i18n) — Phase 0 scaffolding.** Stood up an extensible, offline-first
  multi-language foundation. **No user-visible change yet** — existing English copy is externalized
  in the following phases; this phase only wires the plumbing.
  - **`vue-i18n` v11** (Composition API) + **`@intlify/unplugin-vue-i18n`** wired into Vite. A new
    **`src/core/i18n.ts`** bundles `en` eagerly (first paint never waits on a fetch — a printer host
    is usually offline) and **lazy-loads** every other locale on demand.
  - **Namespaced catalogs** under `src/locales/<code>/` (`common` / `shell` / `firmware` /
    `input-shaping` / `motor-drivers`), mirroring the widget code-split. **Drop-in extensibility:** a
    language becomes selectable the moment its folder exists — no component edits.
  - **Type-safe keys** — `en` is the schema source (`src/types/i18n.d.ts`), so `t('…')` is
    autocompleted and a wrong key fails `npm run type-check`.
  - **Detection** (stored → browser → `en`) + `localStorage` persistence, a reactive
    `<html lang/dir>` update on locale switch, and a **`LanguageSelect`** in the header (reusing
    `ComboSelect`) that stays hidden until a second locale ships.
  - **`latn` (Western) digits pinned for Arabic** and RTL declared in the locale metadata, ahead of
    the Arabic phase; per-locale `numberFormats` / `datetimeFormats` established.
  - **CI/dev tooling:** `npm run i18n:keydiff` (a structural key-diff gate — every locale must carry
    exactly the `en` key set; now a CI step) and `npm run i18n:pseudo` (pseudo-localization to
    surface text-expansion / RTL overflow and any un-externalized strings).

## [0.73.0] - 2026-06-05

### Changed

- **Shared UX kit (#113).** Continued de-duplicating cross-widget code into `components/ui/` +
  `core/`: extracted **`describeError`** (the byte-identical backend-unreachable message helper,
  now shared by the Firmware + Motor Drivers widget roots) and **`LogPane`** (the terminal-style
  `bg-ink` log box with per-line coloring, replacing three hand-rolled copies in the Firmware
  widget). These join the already-shared **`WidgetTabs`** (#112) and **`ComboSelect`** (#120).

  *Intentionally not consolidated:* the per-widget `HelpNote`/`HelpIllo` (generic-izing them would
  churn dozens of call sites across three widgets for no user benefit, and each binds to its own
  `help.ts`), a shared `ConfirmAction` (it would refactor the safety-critical gated-write confirm
  flows for no functional gain), and a `chartTokens` map (the chart hex are already byte-identical
  to the brand tokens, so it's a no-op visually).

### Added

- **Firmware Manager — Guided new-board wizard (#118).** A new **🧭 Guided** tab walks a new
  control board through four steps — detect the board, configure & build a profile, add & assign
  the device, then build & flash and verify it's in sync with the host. Each step reflects the
  **live** firmware state (it turns green when satisfied) and deep-links into the tab where you do
  it; it doesn't duplicate the build/flash logic or bypass any confirm. The widget now lands on
  Guided on first run when no board is set up yet, mirroring the other widgets' first-run flow.

### Changed

- **Input Shaping — the result is reunited with the action (#116).** The recommended shaper,
  A–F measurement grade, frequency-response chart and shaper table now render in **every working
  view** — including **Guided**, which previously showed only per-step pass/fail badges and hid
  the rich result the wizard had just computed. A pinned **“printer.cfg ready”** bar (captured
  axes + 📋 Copy + 💾 Archive) now sits at the top of every working view, so after a capture the
  widget's payoff is one tap away instead of buried below the on-printer panels. *(The optional
  Live-panel section grouping is a minor follow-up.)*

### Changed

- **Sidebar entries stay on one line, and the Firmware widget is renamed to “Firmware Manager” (#135).**
  After per-widget icons were added (#121), the Firmware entry's long label wrapped next to the
  icon, making the button look oversized. Sidebar nav items now use a fixed-width icon slot + a
  truncating single-line label, so every entry is the same compact height. The widget's display
  title is now **Firmware Manager** (it builds, flashes, and manages firmware across MCUs — not
  only "upgrades"); its id/route (`firmware-upgrade`) is unchanged.

### Added

- **App shell — deep-linking, mobile navigation, and wayfinding (#121).**
  - The current view is now synced to `location.hash` (e.g. `#motor-drivers`), so a widget page
    can be **bookmarked and survives a reload** — back/forward work too. (The empty Dashboard
    clears the hash cleanly.)
  - On narrow screens the sidebar is now an **off-canvas drawer** with a ☰ toggle in the header
    and a tap-to-dismiss backdrop — previously there was *no* navigation at all below the `md`
    breakpoint (a portrait tablet had no way to switch widgets).
  - Each widget carries its own **sidebar icon** (`WidgetDefinition.icon`: 🔧 / 📈 / ⚙) instead of
    the same generic glyph for all.

### Removed

- Dead `spanClass` grid logic in `WidgetFrame` (the shell always renders a single column, so it
  never applied).

### Added

- **Accessibility pass — completed (#114).** Accessible names on the shared primitives: the
  `WidgetTabs` tablist (`aria-label="Views"`) and the `ComboSelect` search input + options
  listbox. This closes out the a11y review item: the resonance/vibration **charts already carry
  `role="img"` + `aria-label`**, the motor sparkline is `aria-hidden` (its value is shown as
  text), **keyboard focus rings** shipped in v0.65.1 (#115), and the dense Configure/External
  firmware screens gained touch-accessible help in v0.69.0 (#117). Status badges convey state
  with text + symbols, not color alone.

## [0.69.0] - 2026-06-05

### Changed

- **Firmware Upgrade — information-architecture reorg (#117).** The widget now uses the house
  **`WidgetTabs`** strip — **🩺 Status / 🔧 Configure / 🖥 Devices / 📦 External** — instead of a
  full-screen mode swap + footer buttons, so every area is one tap away (and navigation matches
  the other widgets). **External firmware** is promoted from a buried last-child of the Devices
  manager to its own top-level tab. The Configure and External screens gained touch-accessible
  **`HelpNote`** explanations (previously only hover `title=` tooltips existed there).

## [0.68.2] - 2026-06-05

### Fixed

- **The motor dropdown showed only the first 50 motors (#130).** `ComboSelect` capped the rendered
  list at 50, so with no search text you couldn't reach the rest — bad when you don't remember a
  model name and want to browse. It now renders the full filtered list (the dropdown scrolls), is
  taller for easier browsing, scrolls the highlighted option into view during ↑/↓ keyboard
  navigation, and gives each combobox instance unique option ids (fixes a latent duplicate-id
  across the per-stepper pickers).

### Changed

- **Quick-win copy/naming fixes (#122).** Resolved several small inconsistencies from the UX
  review: Input Shaping's fourth view is now consistently **🕘 History** (tab label aligned with
  the intro + help topic); the Analyze tab's compare button is **⇄ compare CSVs** to distinguish
  it from the Live "compare belts" tool; the Firmware Configure screen's `help` checkbox is now
  **option docs** (distinct from the standard ℹ help layer) and its build button is **build
  profile** (vs the per-device build on Status — and the Devices caption no longer contradicts
  it); the Firmware empty state is now an actionable **"+ Add your first board →"** button.

## [0.68.0] - 2026-06-05

### Changed

- **Motor Drivers — lower card density + earlier wizard access (#119).** Each driver card now
  keeps only the live-tuning essentials inline (chopper mode, microsteps, temperature, StallGuard);
  the secondary specs (sense resistor, interpolation, interface, current cap, capability chips)
  collapse behind a per-card **▸ details** toggle. The Dashboard / 🧭 Guided tab strip now shows
  as soon as the printer is reachable (not only after drivers load), so the wizard is discoverable
  from the start. The advanced register editor's toggle uses a distinct **🛠** glyph so it no longer
  collides with the recommend panel's ⚙.

## [0.67.0] - 2026-06-05

### Changed

- **Navigation converged on one shared tab strip (#112).** A new generic `components/ui/
  WidgetTabs.vue` (the persistent top tab strip, active = `bg-brand-cyan ring-2 ring-ink`,
  type-safe over the tab-id union, ARIA `tablist`/`tab`) replaces the bespoke per-widget strips.
  Input Shaping and Motor Drivers now use it, so navigation looks and behaves identically across
  widgets. (Firmware Upgrade adopts it as part of its IA reorg, #117.)

### Added

- **Shared `ComboSelect` dropdown/combobox primitive (#120).** A reusable typeahead select
  (`components/ui/ComboSelect.vue`): one control that opens a filtered dropdown with keyboard
  navigation (↑/↓/Enter/Esc), ARIA `combobox`/`listbox`/`option` roles, optional clear, and a
  capped result list — the convention for every long option list going forward.

### Changed

- **The Motor Drivers motor picker is now a dropdown** instead of an always-open inline list of
  200+ rows. It uses the new `ComboSelect` (search by model or maker; specs shown per option),
  so a card stays compact until you actually pick. Future long pickers (filaments, boards,
  profiles) should reuse the same primitive.

### Added

- **Keyboard focus is now visible across the app (part of #115, accessibility).** Every
  interactive element (links, buttons, summaries, inputs, selects) gets a clear `brand-cyan`
  focus-visible outline. It uses `outline` (not `box-shadow`, so it never fights the brutal
  shadow) and only shows for keyboard navigation, leaving the dense pointer UI unchanged.

### Fixed

- **Touch targets on tablets (part of #115).** Many compact buttons (notably the firmware
  flash/build actions shrunk to `text-[10px]`) were well under the ~44px tap minimum. Branded
  buttons (`.nb-btn`) now get a 44px min-height on coarse-pointer (touch) devices only, so the
  printer-side tablet is usable while the desktop layout stays compact. (The cosmetic button-size
  normalization follows in the per-widget reorg PRs.)

## [0.65.0] - 2026-06-05

### Fixed

- **Firmware flashing now requires explicit confirmation (#111, P0).** Every flash entry point —
  per-device **flash** / **build & flash**, the **batch** flash actions, and the **Beacon** probe
  flash — previously wrote firmware **immediately on click**, with no preview or confirm, while the
  help text promised FilaMind "confirms before irreversible steps". Flashing is destructive (a
  mid-flash interruption can brick a board), so this was a safety gap. A new `FirmwareFlashConfirm`
  dialog now stands in front of every flash: it previews the flash plan (`command` + warnings +
  ready/blocked, via the existing `fetchFlashPlan`) for a single device, lists the affected devices
  for a batch, and requires an "I understand…" acknowledgement before anything writes. A plan that
  reports `ready: false` (e.g. a print is running) blocks the action. This brings Firmware in line
  with Motor Drivers and Input Shaping, which already gate every write.

### Removed

- The orphaned `FirmwareFlashPanel.vue` (imported nowhere) — its plan→confirm→flash pattern is now
  served by the gated flash path above, removing a second, dead flash UI.

### Added

- **Motor Drivers — register-editor polish (P10c, #102).** Completes the advanced editor:
  - **CoolStep as a single toggle.** CoolStep is a coupled five-register feedback loop, so
    instead of five raw boxes the editor offers one **enable / off** control that applies the
    a community-vetted set (`semin 2 / semax 4 / seup 3 / sedn 2 / seimin 1`) or
    disables it (`semin 0`) — via a new gated `POST /api/drivers/coolstep`, with its own
    illustrated help note.
  - **StallGuard polarity hints.** The `sgthrs` / `sg4_thrs` / `sgt` rows now show the per-model
    polarity inline ("higher = more sensitive" vs the signed `sgt`'s "lower = more sensitive"),
    so the sensitivity direction isn't backwards on SPI drivers.
  - A **`toff` pairing note** (if you set `toff` to 1, keep `tbl` ≥ 1).

## [0.63.0] - 2026-06-05

### Added

- **Motor Drivers — advanced register editor (P10b, #102).** Each driver card gains a
  **⚙ tune registers (advanced)** panel that edits the safe subset of its TMC registers live,
  driven entirely by the server's `field_policy` (the browser never decides what's editable or
  the bounds):
  - chopper timing (`toff` / `tbl` / `hstrt` / `hend`), StealthChop PWM (`pwm_grad` / `pwm_ofs`
    / `pwm_freq` / …), CoolStep (`semin` / `semax` / …), StallGuard sensitivity, and the
    StealthChop↔SpreadCycle crossover threshold **in mm/s** (Klipper does the TSTEP conversion
    via `VELOCITY=`, and refuses it on a clock-less driver like the 2660);
  - the right control per field — number (with the server's clamp range), toggle, select, or a
    mm/s field — with **per-field confirm** on riskier knobs, and non-editable `driver_*`
    registers shown read-only beneath;
  - a **"↺ reset to config"** (`INIT_TMC`) undo and a persistent "live only — a restart restores
    it" note; raw current-scaling and protection registers are not editable here.
  - New `POST /api/drivers/field` (gated + server-clamped) and `GET /api/drivers/field-policy/{model}`.

## [0.62.0] - 2026-06-04

### Added

- **Motor Drivers — register-edit safety foundation (P10a, #102).** A new server-side
  `field_policy` module is the single source of truth for which TMC registers may be edited
  live and within what bounds — the load-bearing safety layer for advanced-register editing,
  because `SET_TMC_FIELD VALUE=` *silently mask-truncates* out-of-range values rather than
  erroring. It provides:
  - an **allowlist** (only catalogued fields are editable; everything else is display-only);
  - a **per-field clamp** whose range is derived from the register **bit-mask** (so it provably
    matches the silicon), with **per-model signedness** — `sgt` is a signed −64…63, while
    `sgthrs` / `sg4_thrs` are unsigned 0–255;
  - a **blocklist** of raw current-scaling (`irun`, `globalscaler`, `vsense`, …) and
    protection-defeat (`diss2g`, `test_mode`, `overvoltage_vth`, …) fields, plus `mres` /
    `microsteps` (which would desync Klipper's step distance), that are never written live;
  - a **per-model current cap** `I_cap = min(code_cap[model], motor rating)` — the TMC2240 cap
    is computed from its `rref` — surfaced per driver as `current_cap` on `/api/drivers/status`.

### Changed

- The sensorless StallGuard write (`POST /api/drivers/stallguard`) now **enforces the field
  range server-side** (the client's `max=` was not trusted): a 2209 `sgthrs` of 300, or a signed
  `sgt` of 64, is rejected before any g-code is sent.
- Driver writes and test-homes are now refused while the printer is **printing, paused, or in an
  error state** (previously only while actively printing).
- `/api/drivers/status` records gained `rref` and `current_cap` per driver.

### Fixed

- **The current-cap warning used the driver's sanity-ceiling, not the real limit (#102).** A
  TMC5160's catalog cap (10.6 A) is only a board sanity ceiling, so the dashboard would show
  "≤ 10.6 A" and not warn until ~9.5 A — dangerously permissive. The "near cap" warning and the
  cap label now use the effective `current_cap` (min of the model code cap and the assigned
  motor's rating), so once a motor is assigned the real motor-bound limit drives the warning.

## [0.61.2] - 2026-06-04

### Fixed

- **Physical-endstop switch state could show `—` on printers that key endstops by stepper name
  (#106).** `GET /api/drivers/endstops` returns Moonraker's raw keys, which are `stepper_x` on
  some printers (the SV08) and the bare axis letter `x` on others. The P9 physical-homing panel
  looked up only the axis letter, so the live switch state wouldn't render on the former. A new
  unit-tested `endstopStateFor()` tries the stepper section name first, then the axis letter.

## [0.61.1] - 2026-06-04

### Fixed

- **Homing classifier missed sensorless when the endstop pin had whitespace after the colon
  (#104).** Klipper parses `endstop_pin` as `chip:pin` split on the first colon with whitespace
  stripped from each side, so `tmc2209_stepper_x: virtual_endstop` (a stray space — present
  verbatim in the SV08's own `printer.cfg`) is a valid sensorless virtual endstop. The P9
  classifier used an exact `:virtual_endstop` substring test and wrongly classified that axis
  as a **physical endstop**. It now normalises the pin the way Klipper does (split + strip,
  case-insensitive), so spaced and unspaced forms classify identically. Caught by live-verify
  on the SV08, where `stepper_x` (spaced) was mislabelled while `stepper_y` (unspaced) was not.

## [0.61.0] - 2026-06-04

### Added

- **Motor Drivers — homing coverage (P9, #101).** Each axis's homing method is now classified
  from its `[stepper_*].endstop_pin` using Klipper's own rule, and surfaced on the card as a
  method-aware **🏠 homing** panel instead of assuming "has a StallGuard register ⇒ sensorless":
  - **Physical endstop** → live switch state (open / TRIGGERED), an on-demand **↻ check**, and a
    plain gated **test-home** (the switch stops the move, so a softer warning than sensorless).
  - **Sensorless (StallGuard)** → the StallGuard tuner, now with **per-model polarity**: the
    signed `sgt` register (TMC2130 / 5160 / 2660) uses its true −64…63 range where _lower_ is
    more sensitive, while `sgthrs` / `sg4_thrs` (2209 / 2240) stay unsigned 0–255 where _higher_
    is more sensitive — so the control no longer feels backwards on SPI drivers.
  - **Z probe** → a pointer to the bed-leveling tools (no StallGuard to tune here).
  - **Virtual / shared** → a clear note; extra motors on a shared rail (a second Z, the extruder)
    show no homing UI.

  The sensorless tuner (and the Guided wizard's sensorless step) now appear **only** for axes that
  actually home sensorless — fixing the case where a probe-homed Z or a switch-homed axis on a
  StallGuard-capable driver wrongly offered sensorless tuning. New `GET /api/drivers/endstops`.

## [0.60.0] - 2026-06-03

### Added

- **Firmware Upgrade widget — built-in help layer (#82).** Per the project's widget-UX rule
  (already used by Input Shaping and Motor Drivers), the Firmware Upgrade widget now has a
  collapsed help row: a **glossary**, **"what's this?" explanations** for each section
  (host/MCU sync, toolchain badges, services, devices, flashing) with **inline SVG
  illustrations**, and a **"build → flash" quick guide**. Collapsed by default — zero clutter.

## [0.59.1] - 2026-06-03

### Fixed

- **Motor Drivers: a driver with no `stealthchop_threshold` set now shows "SpreadCycle"
  instead of "—".** An unset threshold means Klipper's default of 0, i.e. SpreadCycle — so
  the card reports the real mode rather than an unknown one (e.g. the SV08 extruder). (#85)

## [0.59.0] - 2026-06-03

### Added

- **Motor Drivers P8 — motor synchronization (roadmap complete).** A printer-level panel
  drives the optional **motors_sync** add-on to align the microstep phase of multiple motors
  on one axis (dual / quad-Z, dual-X). It detects whether the add-on is installed; if so it
  offers **Sync motors** / **Calibrate** behind a confirm + crash warning (accelerometer-based,
  moves the toolhead, refused while printing); if not, it explains what it does. This completes
  the Motor Drivers widget roadmap (**P1–P8**).
  - Backend: **`GET /api/drivers/motors-sync`** (availability) + **`POST /api/drivers/motors-sync`**
    (`SYNC_MOTORS` / `SYNC_MOTORS_CALIBRATE`, gated).

## [0.58.0] - 2026-06-03

### Added

- **Motor Drivers P7 — guided tuning wizard.** A new **🧭 Guided** view walks one driver
  through the whole flow in order — **choose axis → assign motor → recommend & apply →
  (sensorless) → done** — with a step breadcrumb, per-step guidance, and Back/Next (the
  sensorless step is skipped automatically when the model doesn't support it). It **reuses the
  same panels** as the dashboard, so there's one source of truth and the same safety gating.
  A Dashboard / Guided mode strip switches between the full dashboard and the wizard.

### Changed

- Motor Drivers intro updated (it's no longer read-only — it inspects, recommends, and applies).

## [0.57.0] - 2026-06-03

### Added

- **Motor Drivers P6 — live monitor.** A per-driver, read-only "live monitor" panel polls
  the driver's telemetry (~1.5 s) and shows **temperature**, **StallGuard load (SG_RESULT)**
  with an inline sparkline, **current scale (CS_ACTUAL)**, and any **fault flags**
  (overtemperature / short / open-load / standstill). The driver only reports this while the
  motor is enabled, so an idle motor shows a hint to move/home the axis. No writes, no motion.
  - Backend: fast, focused **`GET /api/drivers/live/{stepper}`** (one driver's `get_status`,
    no config re-read).

## [0.56.0] - 2026-06-03

### Added

- **Motor Drivers P5 — sensorless-homing helper.** For drivers that support sensorless
  homing, a new panel lets you tune the **StallGuard threshold** (`sgthrs` / `sgt` /
  `sg4_thrs`) and **test-home one axis** — both behind an explicit confirm and refused
  server-side while printing. The test-home carries a loud crash warning (a wrong threshold
  can drive the axis into the frame). Guidance: lower if it stops early, raise if it doesn't
  stop. Shown only where the model actually supports sensorless homing.
  - Backend: **`POST /api/drivers/stallguard`** (validated field + value) and
    **`POST /api/drivers/home`** (`G28 <axis>`, gated).

## [0.55.1] - 2026-06-03

### Fixed

- **Motor Drivers: Revert now fully restores the run current.** `INIT_TMC` re-applies the
  configured register *fields* but does **not** undo a `SET_TMC_CURRENT`, so after applying
  a recommendation the motor stayed at the applied current on Revert. Revert now also issues
  `SET_TMC_CURRENT` with the stepper's **configured** run/hold current (read from the live
  config), so it returns to exactly the pre-apply state. (#93)

## [0.55.0] - 2026-06-03

### Added

- **Motor Drivers P4 — apply tuning.** The recommendation can now be acted on, three ways:
  **copy a printer.cfg block** (always safe, no write); **apply it live** to the driver via
  `SET_TMC_CURRENT` / `SET_TMC_FIELD` behind an **explicit confirm**; or **run AUTOTUNE_TMC**
  when a TMC autotune host add-on is installed. A **Revert** button (`INIT_TMC`)
  restores the configured values, and the dashboard refreshes to show the new live numbers.
  - **Safety:** every live write is **refused server-side while the printer is printing**,
    requires the UI confirm, validates all values (no g-code injection), and is reversible.
  - Backend: `drivers_apply` service + **`POST /api/drivers/config-block` · `/apply` · `/init`
    · `/autotune`**.

### Changed

- The "Recommended tuning" panel is no longer preview-only — it now offers copy / apply /
  revert / autotune.

## [0.54.0] - 2026-06-03

### Added

- **Motor Drivers P3 — tuning recommender.** Once a motor is assigned to a stepper, each
  card can compute a suggested **run current** plus the StealthChop / SpreadCycle register
  values (**pwm_grad, pwm_ofs, hstrt, hend**) from the motor's datasheet specs and your
  supply voltage — a built-in `motor_constants` physics model, so
  it works **even without any host add-on installed**. The run current defaults to a conservative
  70% of the motor's rating (overridable). Results are shown as a **preview diffed against the
  live config** (changed values highlighted), with the max StealthChop speed; **nothing is
  written to the driver** — applying is a later, safety-gated step (P4).
  - Backend: pure `motor_constants` + `recommender` services; **`POST /api/drivers/recommend`**
    (404 unknown motor, 422 if the motor lacks the needed datasheet specs).

## [0.53.1] - 2026-06-03

### Fixed

- **Motor picker showed stale results while searching.** The baked motor catalog had 5
  duplicate entries (the same LDO models appear in two source `.cfg` files with identical
  specs), so the picker's `v-for` keys weren't unique and Vue mis-tracked the list as you
  typed. The catalog is now **deduplicated by model** (202 unique motors), the picker uses
  a robust key, and a regression test guards against duplicate models. (#89)

## [0.53.0] - 2026-06-03

### Added

- **Motor Drivers P2b — motor picker.** Each driver card now lets you assign the stepper
  **motor** wired to that axis from a built-in catalog of **200+ motors** (searchable by
  model or manufacturer). The assigned motor's datasheet specs — holding torque, rated
  current, resistance, inductance — show on the card, and the choice is **persisted on the
  printer** (`<data_dir>/motor-mapping.json`). This sets up the upcoming current/register
  recommender; it changes nothing on the driver by itself.
  - Backend: motor database baked to `backend/app/data/motor_catalog.json` (via
    `scripts/bake_motor_catalog.py` from a source CSV); new endpoints
    **`GET /api/drivers/motors`** (the catalog) and **`GET`/`POST /api/drivers/mapping`**
    (read / assign). `GET /api/drivers/status` now attaches the assigned `motor` per driver.
  - A "what's this?" help note explains why assigning a motor matters.

## [0.52.0] - 2026-06-03

### Added

- **Motor Drivers P2a — driver capability map.** Each driver card is now annotated with
  authoritative reference data for its TMC model, from a curated capability catalog
  (verified against the Klipper driver code): **communication interface**
  (UART / SPI / both), the **current cap**, and accurate **capabilities** (StealthChop /
  SpreadCycle / CoolStep / StallGuard / temperature) — so the chips reflect what the model
  truly supports rather than only what the config exposes. A ⚠ hint flags a run current
  near the model's rated cap, and a new "where the model facts come from" help note explains
  the source.
  - New endpoint **`GET /api/drivers/catalog`** returns the full capability map (keyed by
    model, with aliases like 2225→2208 / 2226→2209 / 5161→5160), backing this and the
    upcoming motor picker.
  - Data baked to `backend/app/data/driver_catalog.json`; covers TMC2208 / 2209 / 2130 /
    2240 / 2660 / 5160 (and aliases). Unknown models still render fully from live config.

## [0.51.0] - 2026-06-03

### Added

- **New widget — Motor Drivers (P1: read-only dashboard).** A live inventory of every
  TMC stepper driver on the printer, discovered straight from the Klipper config — one
  card per motor (X / Y / each Z / extruder…). Each card shows the driver model, run &
  hold current (live vs configured), chopper mode (SpreadCycle / StealthChop + threshold),
  microsteps, sense resistor, StallGuard threshold, live temperature (or “no sensor” on
  models without one), a live health badge (idle / ok / warning / fault from `drv_status`),
  capability chips, and a collapsible advanced-register view.
  - **Generic across every Klipper printer** — drivers are detected from config, not
    assumed; all TMC models are handled (2209 / 2208 / 2130 / 2240 / 5160 / 2660…), with
    model-specific fields (temperature sensor, StallGuard register name) resolved from
    what the running config actually exposes.
  - Built-in **help layer** (the project UX rule): a glossary, per-section “what’s this?”
    notes with inline SVG illustrations, and a “how to read this” step list.
  - Backend: `drivers_service` + **`GET /api/drivers/status`**.

### CI

- **Releases now publish automatically.** Pushing a `vX.Y.Z` tag triggers
  `.github/workflows/release.yml`, which creates the GitHub Release from the matching
  `CHANGELOG.md` section. Fixes release publishing that had silently stalled at v0.42.1
  (11 tags with no Release; now backfilled). (#80)

### Docs

- **CONTRIBUTING**: documented three project norms — the widget-UX rule (every widget
  ships explanations + practical steps + inline SVG illustrations), the
  discovered-problem → typed GitHub issue → patch-PR rule, and the release process.

## [0.50.1] - 2026-06-03

### Fixed

- **Firmware Upgrade widget no longer goes blank / shows a bare "Failed to fetch".** When the
  backend was briefly unreachable, the silent 6 s refresh cleared the error and left no fresh
  data, so the widget rendered an **empty panel** (and the initial failure showed only the raw
  `Failed to fetch`). It now keeps the last good data on a transient refresh failure, shows a
  clear **"Cannot reach the FilaMind backend — check that the filamind-flow service is running"**
  message with a **Retry** button, and a fallback line instead of a blank panel.

## [0.50.0] - 2026-06-03

### Added — Input Shaping: every test type feeds the Audit (UX overhaul, 7 of 7 — complete)

- **The Audit now aggregates every result, not just shaper runs.** Each live tool — accelerometer
  noise, belt comparison, axes-map, sustain frequency, and the vibrations profile — records an
  entry when it completes, rendered as a per-property card alongside the shaper calibrations and
  the archived configs/captures. One organized, engineered place to review every test by property.
- New pure record builders in `audit.ts` (one per tool, reusing the existing belt / axes-map /
  result verdicts) with unit coverage; `ResonanceFromPrinter` emits a `recorded` event per tool.
- **This completes the Input Shaping widget reorganization** (v0.45.0 → v0.50.0): four-view IA,
  inline help + illustrations, per-tool motion confirms, a persistent host archive, a unified
  upload/host file source, and the aggregated per-property Audit.

## [0.49.0] - 2026-06-03

### Changed — Input Shaping: History becomes the aggregated Audit (UX overhaul, 6 of N)

- **The History tab is now "Audit"** — one place that aggregates past results, merging this
  browser's records with the on-host **archive** (saved configs + captures). Each result renders
  as a card with its properties in **separate labelled fields** (the shaper factor breakdown,
  grade, and trend ▲/▼ vs the previous same-axis run), newest-first.
- New pure `audit.ts` (unified `AuditRecord` model + per-kind retention + a one-time, idempotent
  fold-in of the legacy grade-history — additive, the old localStorage is never cleared) with a
  unit-test suite. Shaper analyses now also record an audit entry.
- The other live-tool results (noise / belts / axes-map / sustain / vibrations) join the Audit in
  the next release.

## [0.48.0] - 2026-06-03

### Added — Input Shaping: unified CSV source + archive browser (UX overhaul, 5 of N)

- **One place to pick the CSV to analyse.** The Analyze view now has a `CsvSourceChooser` with a
  segmented **📤 Upload** ⟷ **🖥 From printer** control. "From printer" lists both the resonance
  CSVs on the host *and* the persistent archive, so the previously-separate upload and host-import
  paths are unified — all flowing into the one analysis path (and carrying the advanced params
  either way).
- **Archive browser.** Saved runs are listed with per-file **download** and **delete**, a 💾 **save**
  on each host capture, and a 💾 **Archive** button beside the config block's Copy — so a generated
  `[input_shaper]` or a scan CSV can be kept as a deletable historical record. (Backend from v0.47.0.)
- The host-file list moved out of **Live tools** (now motion-only) into the chooser, removing the
  duplication. `/analyze-file` now also accepts `max_smoothing` / `damping_ratio` so a local-file
  analysis honours the same knobs as an upload.

## [0.47.0] - 2026-06-03

### Added — Input Shaping: persistent on-host archive (backend, UX overhaul 4 of N)

- **A persistent archive of captures + generated configs.** New `shaper_archive` service +
  `/api/shaper/archive` routes keep recent resonance CSVs and generated `[input_shaper]`
  configs under `<data_dir>/input-shaper-archive/<run_id>/`, so results survive a reboot and
  the browser — reviewable, **downloadable**, and **deletable** as a historical record. A
  single `index.json` stores only a compact per-run summary (never the multi-thousand-element
  PSD / spectrogram arrays), and retention is bounded **per kind** (`FILAMIND_SHAPER_ARCHIVE_KEEP_N`,
  default 20) to stay light on the SD card.
- Routes: `GET /archive` (list), `GET /archive/{id}` (+ inline config), `GET /archive/{id}/file/{name}`
  (download), `DELETE /archive/{id}`, `POST /archive/save-config`, `POST /archive/save-file` (copy a
  host CSV in). All path-guarded (name regex + realpath containment), atomic writes.
- The browser UI for the archive (review / save / delete + the unified file source) lands next.

## [0.46.1] - 2026-06-03

### Changed — Input Shaping: per-tool motion confirm (UX overhaul, 3 of N)

- **Each on-printer tool now has its own "moves the toolhead — I'm ready" confirm.** Previously a
  single checkbox armed the live test, the belt comparison *and* axes-map together — so ticking it
  for a quick live test also armed the much larger belt sweep. The live test, belt comparison and
  axes-map are now three self-contained panels, each with its own confirm + run button (consistent
  with the Sustain and Vibrations panels). Safer and clearer; the shared concurrency lock and the
  backend print-guard are unchanged.

### Added

- Backend guard tests covering every on-printer entrypoint (live / belts / axes-map / sustain /
  vibrations / noise) refusing to run while the printer is printing.

## [0.46.0] - 2026-06-03

### Added — Input Shaping: built-in explanations + illustrations (UX overhaul, 2 of N)

- **The widget now teaches as it works.** A collapsed-by-default **"ℹ what's this?"** note sits
  beside each section — glossary (6 core terms), how to read the A–F grade, the frequency chart,
  the shaper table, the config block, and every live tool (noise / belts / axes-map / sustain /
  vibrations) plus a "guided vs. manual" primer. Each expands a short plain-language explanation
  and, where it helps, a **hand-drawn SVG illustration** (resonance peak, shaper impulses, belt
  pair, sensor axes, speed sweep, capture→analyze→apply flow). All copy lives in one `help.ts`,
  with the numbers anchored to the actual grading thresholds.
- The cryptic frequency-chart caption (`Hz · left PSD · right vibration reduction`) is replaced
  with plain wording (`frequency (Hz) → · solid = measured · faint = shaper leftover`).
- Collapsed by default, so the default view stays uncluttered.

## [0.45.0] - 2026-06-03

### Changed — Input Shaping: widget reorganized (UX overhaul, 1 of N)

- **Four clear views instead of six stacked toggles.** The Input Shaping widget now opens on a
  tab strip — **🧭 Guided** (the default landing view), **📈 Analyze**, **🔴 Live tools**,
  **🕘 History** — so only one task is on screen at a time instead of a long scroll of
  independently-toggled panels. The guided wizard is kept mounted, so an in-progress run
  (including its minutes-long on-printer captures) survives a tab switch. Behavior-preserving:
  every existing tool, the result view, and the combined `printer.cfg` block are unchanged —
  just better organized. First step of a multi-PR Input Shaping UX overhaul.
- **CI now fails on a stale `frontend/dist`.** The printer host serves the pre-built UI bundle
  straight from git, so a forgotten rebuild would silently ship an old UI. CI now runs
  `npm run build` and fails if anything under `frontend/dist` differs from what was committed.
  Added a matching PR-template reminder.

## [0.44.1] - 2026-06-03

### Docs — resonance-tuning suite complete (5 of 5)

- Documentation sweep closing out the resonance-tuning suite effort (part 3/3): the ROADMAP
  gains phase 13 (vibrations profile) and the parity section is marked **✅ COMPLETE (5 of
  5)**; the Input Shaping range now reads v0.27.0 → v0.44.0. ARCHITECTURE updated to describe
  the full capture/analysis set (axes-map · sustain frequency · guided wizard · vibrations
  profile); the README feature list already covers it (v0.44.0). No code change.

## [0.44.0] - 2026-06-03

### Added — Input Shaping: vibrations profile UI + wizard (resonance-tuning suite, 5 of 5 — part 2/3)

- **Machine vibrations profile (browser).** A new 📊 panel in the "From the printer" view
  runs the sweep (with adjustable top speed + step) and renders it as a **speed-vs-energy
  curve** (smoothest bands highlighted, resonance speeds to avoid flagged, the recommended
  speed marked), a **polar plot** of vibration energy by travel direction, and an **angle ×
  speed heatmap** — plus the motor **symmetry**, the motor **resonant frequency / damping**,
  and a plain-language verdict. All dependency-free SVG.
- **Guided wizard: the Vibrations step is now measured.** What was a manual "did you see
  VFAs?" self-report now runs the real vibrations profile, gates on motor symmetry +
  low-frequency-noise health, and shows the same profile view inline with ranked
  recommendations (favour ~X mm/s, avoid the peak speeds, re-tension belts if symmetry is low).
  This closes the guided flow end to end: Noise → Belts → Shaper X → Shaper Y → Vibrations →
  Pressure.

## [0.43.0] - 2026-06-03

### Added — Input Shaping: vibrations profile backend (resonance-tuning suite, 5 of 5 — part 1/3)

- **Machine vibrations profile (backend).** New `POST /api/shaper/vibrations-profile` and a
  pure `vibrations_service` (a numpy vibrations computation, reusing
  the vendored Klipper `ShaperCalibrate` for the per-segment PSD — no matplotlib, no Klipper
  host). It sweeps a range of speeds along each kinematic motor angle (0/90 for
  Cartesian/CoreXZ, 45/135 for CoreXY) while `ACCELEROMETER_MEASURE` brackets each constant-
  speed burst, then reports the **smoothest speed ranges**, the **resonance speeds to avoid**,
  the smoothest **travel directions** (polar energy), a motor **symmetry** score, and the
  **motors' resonant frequency + damping**. The whole sweep is one blocking call kept inside
  nginx's 1200s budget by a coarse default speed increment (finer increments take longer).
  Print-guarded; requires a configured resonance tester + accelerometer. The browser UI and
  the guided-wizard integration land in the next two releases.

## [0.42.1] - 2026-06-03

### Fixed

- **Long resonance tests no longer 504.** The nginx `/api/` proxy used the default 60s
  `proxy_read_timeout`, so any operation that moves the toolhead for more than a minute —
  a belt comparison (two full sweeps), a live test, axes-map, or sustain-frequency —
  returned **504 Gateway Timeout** even though the backend was still running and would have
  finished. Raised the `/api/` `proxy_read_timeout` / `proxy_send_timeout` to 1200s in both
  the installer (`scripts/install.sh`) and the deploy template. Added a UI note that live
  tests can take 1–5 minutes. (Existing installs: re-run the installer, or reload the
  updated nginx site, to apply.)

## [0.42.0] - 2026-06-03

### Added — Input Shaping: guided wizard completes the workflow (resonance-tuning suite, 4 of 5)

- The 🧭 guided wizard now covers the full resonance tuning flow with two guided-manual steps
  after the shaper calibration: **Vibrations / VFAs** (a quick "do you see vertical fine
  artifacts?" self-report → keep slicer speeds out of the resonant band, or dig into TMC
  tuning) and **Pressure advance** (a copy-able PA tuning-tower g-code + how to apply the
  result). Frontend-only; the Vibrations step is the seam the measured vibrations profile
  (next) plugs into.

## [0.41.0] - 2026-06-03

### Added — Input Shaping: guided tuning wizard (resonance-tuning suite, 3 of 5)

- **🧭 Guided tune.** A step-by-step wizard that walks Noise → Belts → Shaper X → Shaper Y
  with automated **pass/fail gates** (reusing the existing scorers — the A–F grade, the belt
  verdict and the noise grade) and concrete **next-step suggestions** per result. A progress
  rail, per-step verdicts + ranked recommendation cards (do-now / consider / ok), and
  Next / Re-run / Skip controls; the X and Y captures flow into the same combined
  `[input_shaper]` block and the grade-tracked history. Pure, unit-tested `guided` (state +
  gates) and `recommend` modules; reuses the existing `/api/shaper/*` endpoints (no new
  backend).

## [0.40.0] - 2026-06-03

### Added — Input Shaping: sustain frequency (resonance-tuning suite, 2 of 5)

- **Hold-a-frequency hands-on diagnostic.** A new `🎯 sustain frequency` action buzzes the
  toolhead in place near a chosen frequency for a few seconds — a slow, narrow
  `TEST_RESONANCES` sweep, so **no custom macro or printer-config change is needed** — and
  you touch belts / toolhead / frame to feel which part is the resonance source. Returns a
  frequency×time **spectrogram** + an **energy-vs-time "touch timeline"** (the cyan dip marks
  when a touch reduced the vibration) + a verdict on whether the requested frequency
  dominated. New backend `POST /api/shaper/excitate` (moves the toolhead in place;
  print-guarded). Pure-numpy STFT in `spectrogram_service`.

## [0.39.0] - 2026-06-02

### Added — Input Shaping: axes-map calibration (resonance-tuning suite, 1 of 5)

- **Accelerometer orientation detection.** A new `🧭 axes map` action jogs the toolhead
  ~30 mm in +X/+Y/+Z, integrates the accelerometer signal to velocity, and detects the
  Klipper `axes_map` to use (e.g. `-z, y, x`) plus per-axis tilt + confidence — so every
  Input Shaping graph reads with X/Y/Z aligned. Reconstructs the no-signal axis on 2-axis
  / bed-slinger machines. Shows a paste-ready `[<chip>] axes_map: …` (Copy) + a
  "matches your config?" verdict + a velocity-sequence chart.
- New backend `POST /api/shaper/axes-map` (**moves the toolhead**; print-guarded; auto-homes).
  The pure-numpy detection (`axes_map_service`) computes the accelerometer axes-map; the
  capture is orchestrated over Moonraker REST with
  `ACCELEROMETER_MEASURE` bracketing the moves — the reusable capture spine for the coming
  sustain-frequency and vibrations features.

## [0.38.1] - 2026-06-02

### Fixed

- **Portable Mainsail sidebar link.** The installer hard-coded the sidebar link to
  `http://<hostname>.local:8090`, which is dead for any client that can't resolve mDNS
  (Windows without Bonjour, Android, a different subnet, VPN) — a real user saw it land
  on an unreachable `…​.local:8090`. It now defaults to the primary **LAN IP** (resolves
  everywhere on the network), opens in a new tab, and accepts a `FILAMIND_PUBLIC_HOST`
  override (`FILAMIND_PUBLIC_HOST=printer.example` or a fixed IP). The app itself was
  always fine — same-origin — so the broken case was purely the link host. (A fully
  host-preserving subpath link, working at *any* address, is the next step.)

## [0.38.0] - 2026-06-02

### Added

- **Grade-tracked calibration history.** The Input Shaping history now records the
  measurement quality grade (A–F + score) for each calibration and shows it inline,
  with a trend arrow (▲ improved / ▼ declined) versus the previous test of the same
  axis — so the effect of a mechanical fix on measurement quality is visible at a
  glance. Frontend-only; entries saved before v0.38 (without a grade) still load.

## [0.37.0] - 2026-06-02

### Added

- **CoreXY belt comparison.** A `🟰 compare belts` action in the Input Shaping "from the
  printer" panel runs a resonance test along each belt diagonal — `(1,1)` and `(1,-1)` —
  and overlays the two responses with a verdict (belts matched vs a tension mismatch,
  judged from the dominant-peak frequencies), so you can balance CoreXY belt tension.
  New backend route `POST /api/shaper/compare-belts` (print-guarded; **moves the
  toolhead**, two sweeps).

## [0.36.0] - 2026-06-02

### Added

- **Accelerometer noise pre-check.** A motion-free `MEASURE_AXES_NOISE` button in the
  Input Shaping "from the printer" panel reads the accelerometer's idle noise floor and
  grades it (quiet / elevated / too noisy — Klipper's normal range is ~1-100), so you
  can validate the sensor mount before running a resonance test. New backend route
  `POST /api/shaper/noise` (print-guarded; does **not** move the toolhead).

### Documentation

- Brought the docs in step with the shipped features: documented the **Input Shaping**
  widget in `README.md` + `ROADMAP.md`, refreshed the version badge, filled in the
  `/api/shaper/*` endpoints and the firmware / resonance `FILAMIND_*` settings in
  `backend/README.md`, refreshed `docs/ARCHITECTURE.md`, and added a "keep docs in step
  with features" rule to `CONTRIBUTING.md`.

## [0.35.0] - 2026-06-02

### Added — Input Shaping advanced insights

- **Measurement quality grade (A–F).** Each capture gets a letter grade + a 0–100
  score from five factors — peak clarity (signal-to-noise), residual vibration,
  smoothing, frequency band, and single-vs-multi resonance — with a per-factor
  breakdown and a plain verdict, so a trustworthy, well-tuned result is obvious at a
  glance from one that needs a re-test.
- **Visual diagnostics + fixes.** Rule-based cards map the measurement to the likely
  mechanical cause and the fix, each with a hand-drawn, dependency-free SVG
  illustration: low frequency → tighten belts / stiffen frame; high smoothing →
  retune; multi-hump → re-seat the toolhead; weak peak → secure the accelerometer;
  plus a cross-axis card that flags a large X-vs-Y stiffness mismatch once both axes
  are captured.
- **Annotated frequency-response chart.** The dominant resonance peak is marked
  (vertical line + dot + a "57 Hz" label) and the PSD noise floor is drawn as a faint
  reference line, so the meaningful peak stands out from the noise.
- The **Recommended** banner now shows the suggested `max_accel`.

### Changed

- The plain-text hint list is replaced by the richer grade + diagnostics. The
  `interpret` helper is superseded by pure, unit-tested `grade` + `diagnose` modules.

## [0.34.0] - 2026-06-02

### Changed / Fixed — portability (works for any user on any printer, not just the dev's)

- **Import finds resonance CSVs beyond `/tmp`.** Default scan dirs are now
  `/tmp,~/printer_data/config,~/printer_data/config/input_shaper` (override with
  `FILAMIND_RESONANCE_DIRS`), so captures saved by the usual input-shaper flows show
  up — not just the volatile `/tmp` (which is wiped on reboot and empty off-host).
- **Large live captures are no longer silently truncated.** The host-file read cap
  was 20 MB; a long sweep exceeds that (a real SV08 capture was 30 MB), feeding the
  parser a truncated file. Raised to 128 MB.
- **Deploy templates are consistent + host-portable.** The nginx site, the Mainsail
  `navi.json` and the deploy docs used port 8080 while `install.sh` uses 8090 —
  aligned to 8090. Removed the misleading advice to bake `VITE_*` host URLs into the
  build: the pre-built UI resolves Moonraker/backend/Mainsail from `window.location`
  (same origin), so it already works at whatever IP/hostname you reach it by — no
  host is baked in. (A fully host-preserving Mainsail sidebar link via a subpath
  reverse-proxy is the documented next step.)

## [0.33.4] - 2026-06-02

### Fixed

- **Live resonance test failed to parse the captured CSV** ("the number of columns
  changed from 4 to 2"). Klipper writes the raw accelerometer data from a
  background process, so `TEST_RESONANCES` returns before the (often hundreds of
  thousands of rows) file is fully flushed — the analysis read it mid-write and
  hit a truncated final row. The live test now waits for the file size to
  stabilise before reading it, and the raw-CSV parser tolerates a ragged row.

## [0.33.3] - 2026-06-02

### Fixed

- **Live resonance test failed with "Must home axis first".** `TEST_RESONANCES`
  moves the toolhead to the probe point, which needs homed axes. The live test now
  homes the printer (`G28`) first when it isn't already fully homed, then runs the
  test — so the button works from cold.

## [0.33.2] - 2026-06-02

### Fixed

- **Live resonance test wrongly reported "No `[resonance_tester]`".** The guard
  looked for `resonance_tester` in `/printer/objects/list`, but that's a Klipper
  config *section*, not a queryable status object — it never appears there, so the
  live test always refused, even on printers that have it configured (e.g. a Sovol
  SV08 with its toolhead ADXL345). It now checks the parsed `configfile` config,
  where the section actually lives.

## [0.33.1] - 2026-06-02

### Fixed

- **Input Shaping analysis 500'd when `numpy` was missing from the backend venv.**
  A manual `git reset` deploy doesn't run `pip install`, so a host that never ran
  `deploy/install-host.sh` (or the Moonraker update manager) lacked numpy and every
  analysis failed with an unhandled HTTP 500. The shaper helper is now built inside
  the guarded block, so a missing dependency surfaces as a clear 400 instead. (The
  real fix is installing the dependency — run `install-host.sh` / the update
  manager after pulling new backend requirements.)

## [0.33.0] - 2026-06-02

### Added

- **Input Shaping — connected to the printer.** A new "from printer" panel:
  - **Import** the resonance CSVs Klipper already wrote on the host (scans `/tmp`
    by default) and analyse one with a click — no download/re-upload.
  - **Run a live test** — trigger `TEST_RESONANCES` on a chosen axis via Moonraker
    (gated behind a "moves the toolhead" confirm), then auto-analyse the captured
    CSV. Print-guarded; refuses unless a `[resonance_tester]` is configured.

  Backend: `GET /api/shaper/files`, `POST /api/shaper/analyze-file` (path-validated
  to the configured `resonance_dirs`), `POST /api/shaper/live-test`, and
  `MoonrakerClient.run_gcode`. The connected paths are verified locally with a
  mocked Moonraker; running an actual live test needs a printer with an
  accelerometer.

### Added

- **Input Shaping — interpretation hints + calibration history.** Each analysis now
  comes with plain-language guidance: the suggested `max_accel`, warnings for a low
  shaper frequency or high smoothing, and a note when a multi-hump shaper is
  chosen. A browser-local **history** records each calibration (date · axis ·
  shaper @ frequency) so you can watch how an axis drifts over time. Completes the
  Input Shaping widget (phases 1–6).

## [0.31.0] - 2026-06-02

### Added

- **Input Shaping — compare two captures (A ⇄ B).** A new compare panel: load two
  resonance CSVs (e.g. before/after a belt-tension fix, or the same axis re-tested)
  and see them side by side — an overlaid total-PSD chart plus a metric table
  (recommended shaper, frequencies, peak frequency, remaining vibrations,
  `max_accel`) that flags whether **B improved or regressed** versus A.

## [0.30.0] - 2026-06-02

### Added

- **Input Shaping — per-axis X/Y config + advanced parameters.** Analyze the X and
  Y resonance files in turn and the widget accumulates both into a single
  `[input_shaper]` block (`shaper_type_x` / `_y` + frequencies), with chips showing
  which axes are captured and a clear button. A new **advanced** panel exposes the
  knobs the desktop tool hardcodes — `max_freq`, `scv`, `max_smoothing`,
  `damping_ratio` (blank = Klipper's default).

## [0.29.0] - 2026-06-02

### Added

- **Input Shaping — frequency-response chart.** The widget now draws the resonance
  **frequency-response graph** inline as a dependency-free SVG: the X / Y / Z and
  combined PSD curves layered over each shaper's vibration-reduction curve, with
  the recommended shaper accented and the rest dashed — the same picture as
  Klipper's `calibrate_shaper` plot, rendered in the browser.

## [0.28.0] - 2026-06-02

### Added

- **Input Shaping widget (analysis UI).** A new **Input Shaping** sidebar page:
  upload a resonance `.csv`, pick the axis, and Analyze → it shows the recommended
  shaper (e.g. `MZV @ 52.3 Hz`), a table of every tested shaper (frequency,
  remaining vibrations, smoothing, suggested `max_accel`), and a ready-to-paste
  `[input_shaper]` config block with one-click copy. The frequency-response chart
  lands next.

## [0.27.0] - 2026-06-02

### Added

- **Input Shaping — resonance analysis backend.** A new `POST /api/shaper/analyze`
  endpoint runs Klipper's own input-shaper calibration on an uploaded resonance
  CSV (a PSD `freq,psd_x,…` file or raw accelerometer `time,accel_x,…` samples)
  and returns the recommended shaper, every tested shaper's metrics (frequency,
  remaining vibrations, smoothing, suggested `max_accel`), and the full
  frequency-response series for plotting. The math is Klipper's `shaper_calibrate`
  vendored under `backend/app/vendor/klipper_shaper` (GPLv3); it runs serially
  with only numpy, so no printer is required. First slice of the Input Shaping
  widget.

## [0.26.0] - 2026-05-31

### Added

- **Compare two external firmware files side by side.** A `compare A ⇄ B` picker
  at the top of the External firmware section diffs the two files' detected
  properties — app, version, MCU, size, and every baked-in `config` constant —
  into a read-only table that highlights what **changed**, what's **only in A**,
  what's **only in B**, and what's the **same** (with a per-config-key tally). The
  diff runs entirely client-side from the already-inspected properties, so it
  needs no extra request and never touches the files. Appears once two files are
  registered.

### Added

- **External firmware shows the full build config baked into the file (read-only).**
  Beyond the Klipper version, the inspector now decompresses the firmware's data
  dictionary and surfaces every constant compiled into the binary — `MCU`,
  `CLOCK_FREQ`, the reserved USB / SPI / I2C bus pins, `STEPPER_BOTH_EDGE`,
  `ADC_MAX` / `PWM_MAX`, … — in a collapsible, read-only list under each file
  (e.g. an SV08 `.bin` reveals its 14 baked-in settings). These are compiled into
  the machine code and **cannot be edited**: to change them, build a profile in
  Configure and flash that instead — the panel says so explicitly rather than
  implying the values are editable.

## [0.24.1] - 2026-05-31

### Fixed

- **External firmware reads the version from raw `.bin` files too.** Klipper
  stores its version / MCU in a **zlib-compressed data dictionary**, not plain
  strings, so a raw `.bin` (e.g. an SV08 firmware) showed nothing. The inspector
  now decompresses that dictionary (→ `v0.12.0-… · stm32f103xe`).

## [0.24.0] - 2026-05-31

### Changed

- **Optional config options show as normal toggles (no lock).** Klipper's
  "Optional features (to reduce code size)" (`WANT_*`) are gated behind
  `HAVE_LIMITED_CODE_SIZE`, which Klipper auto-selects only for MCUs with **<64 KB
  flash** (`select … if FLASH_SIZE < 0x10000`). They now render as plain toggles,
  matching the reference tool: on flash-limited boards they apply; on roomier
  boards Klipper auto-includes them. (Reverts the 🔒 lock from v0.21.2.)

### Added

- **External firmware: read embedded properties.** On upload (and for existing
  files), the binary is scanned for its embedded **Klipper version** and an **MCU
  hint**, shown read-only ("🔍 read from file: Klipper v… · mcu …").

## [0.23.1] - 2026-05-31

### Fixed

- **External firmware section no longer freezes the page.** The per-file
  flash-target state was created lazily inside a `v-model` during render, which
  looped the renderer once a firmware entry existed. It's now seeded when the
  list loads.

## [0.23.0] - 2026-05-31

### Added

- **External firmware section.** A new section in the Devices manager to register
  pre-built firmware files (`.bin` / `.uf2` / `.elf` / `.hex`) and flash them
  directly — no build step. Upload a file, edit its flash properties (label,
  flash method, bootloader offset, CAN interface, notes), pick a target board,
  and flash; files can also be downloaded or removed. Backed by new
  `/api/firmware/external` endpoints.

## [0.22.0] - 2026-05-31

### Added

- **Per-device Katapult toggle.** Each serial / CAN device in the Devices manager
  now has a **katapult** checkbox (the flag was stored but never surfaced). When
  it's off, a flash **skips the Katapult reboot-to-bootloader** step — for boards
  flashed directly or via `make flash` — matching how the reference tool models
  Katapult per device.

## [0.21.2] - 2026-05-31

### Fixed

- **"Optional" options that can't be set now show as locked.** Turning on the
  *optional* toggle surfaces Klipper's `WANT_*` feature flags; many depend on a
  prerequisite that isn't enabled in the current configuration, so Klipper won't
  let them change. They now render **🔒 locked** (with an explanatory tooltip)
  instead of an ON toggle that did nothing when clicked.

## [0.21.1] - 2026-05-31

### Fixed

- **Config options are easier to toggle.** A bool option's **whole row** is now a
  click target (not just the small badge on the right), with a pointer cursor and
  a hover highlight — so options like *Optimize stepper code…* are obviously and
  reliably controllable. Options that Kconfig locks (forced by another symbol)
  now show a 🔒 and a tooltip explaining why they can't be changed.
- **Browsers always load the latest build.** nginx now serves `index.html` with
  `Cache-Control: no-cache` (and the content-hashed assets as `immutable`), so a
  new deploy is picked up immediately instead of a stale bundle lingering in the
  browser cache.

## [0.21.0] - 2026-05-31

### Added

- **Discovered boards show their bootloader mode** — the Devices manager's
  *Discovered* list now badges each unregistered board with its live mode /
  bootloader (KATAPULT, READY, DFU, …), and no longer offers the Linux host MCU
  as an addable board (it is managed separately).

### Changed

- **Linked bootloader identities are clearer** — a board's attached Katapult /
  DFU identity now renders as an indented, connected sub-card with an *unlink*
  button, instead of a flat badge row; the discovered-board action is labelled
  **🔗 link**.
- **Firmware configurator shows the whole config** — the Kconfig editor no longer
  scrolls inside a fixed-height box; every option is visible and the page scrolls
  normally.

## [0.20.1] - 2026-05-31

### Fixed

- **Configurator no longer 500s when switching processor architectures** (STM32,
  ATSAM, LPC176x, RP2040, PRU, AR100). Those architectures expose Kconfig **menu /
  comment** nodes, which — unlike symbols — have no `help` attribute in
  kconfiglib; reading it raised `AttributeError`. The serializer now reads it
  safely. (Surfaced by v0.18.0 forcing the low-level menus visible.)

## [0.20.0] - 2026-05-31

### Added

- **Inline help** — a *help* toggle renders each option's help text under it
  (previously only a hover tooltip).
- **Profile Info card** — the selected profile's built status, version, and flags
  (linux / avr / CAN bridge) at a glance.
- **Raw symbol names** — a *raw* toggle shows the underlying Kconfig symbol name
  and, for gated options, the dependency that controls them.
- **Kconfig comments** are now rendered in the editor (informational notes that
  were previously dropped).
- Each symbol now carries its **default** value and **dependency** expression,
  surfaced as inline hints under the *raw* / *help* toggles.

### Fixed

- **Read-only options can't be edited.** Symbols selected by another option now
  also disable their dropdown / text field (only the on/off toggle was guarded).

## [0.19.0] - 2026-05-31

### Added

- **Rename a profile** — renames its `.config`, moves any built binary +
  build-info, and rewrites every device that pointed at it, in one step.
- **Duplicate / save-as a profile** — copies a profile's config (and any built
  binary) under a new name to branch from an existing setup.

### Changed

- **Build auto-saves pending edits** — clicking *build* with unsaved Kconfig
  edits now saves them into the profile first, so the compiled firmware always
  reflects what's on screen.

## [0.18.1] - 2026-05-31

### Fixed

- **Downloaded firmware keeps its real filename for profiles with spaces.** The
  ↓ .bin download parsed only the plain `Content-Disposition` form, so a profile
  like "Linux host" (sent by Starlette as the RFC 5987 `filename*=utf-8''…` form)
  fell back to a wrong `.bin` name. It now decodes both forms (→ `Linux host.elf`).

## [0.18.0] - 2026-05-31

### Added

- **Configurator: low-level options are always visible.** The firmware config
  editor now force-enables Klipper's `LOW_LEVEL_OPTIONS` (and
  `HAVE_LIMITED_CODE_SIZE`) gates, so the optimization / low-level menus Klipper
  hides by default always show. Revealed options keep their defaults — a build
  is unchanged unless you edit one.
- **Download the built firmware binary.** Built profiles get a **↓ .bin** button
  (backed by `GET /api/firmware/config/profiles/{name}/artifact`) to download the
  compiled `.bin` / `.uf2` / `.elf` for manual flashing.

### Changed

- README refreshed — it described an "empty scaffold"; it now documents the
  shipped Firmware Upgrade widget.

## [0.17.1] - 2026-05-31

### Fixed

- **Update alert compares the right versions** — a device's **⚠ update** badge
  now compares its **live MCU firmware** (what Moonraker reports the board
  running) against the **host's running Klipper** (`software_version`), instead
  of the repo build version. Both come from the live printer, matching how
  Klipper itself decides host↔MCU sync.

### Added

- Roadmap **Phase 14 — Configurator / profile parity**, capturing the
  profile-creation gaps found vs the reference (rename, duplicate / save-as,
  download the built binary, forced low-level symbols, inline help text, …).

## [0.17.0] - 2026-05-31

### Added

- **Sidebar pages** — the FilaMind sidebar now lists each panel (e.g. **Firmware
  Upgrade**) as its own entry; clicking it opens that panel on its own page. The
  **Dashboard** home is intentionally empty for now, ready for future widgets.
- **Per-device "build & flash"** — a third button on each device card builds the
  assigned profile then flashes it in one go (it only flashes if the build
  succeeded).
- **Outdated-firmware alert** — a device card shows a **⚠ update** badge when its
  flashed firmware differs from the host's Klipper version.

## [0.16.2] - 2026-05-31

### Fixed

- **Per-device flash runs the built firmware directly** — clicking **flash** on a
  device card now flashes its assigned profile (reusing the artifact you just
  built) instead of opening a separate profile-picker. The streamed command log
  appears **right under that device's build / flash buttons**, and the batch log
  under the batch buttons.

## [0.16.1] - 2026-05-31

### Changed

- Slimmed the main screen — removed the per-MCU status rows and the Linux host
  MCU row; the operational **Devices** cards now carry each board's live status.
  The host Klipper row, tool / setup badges, services, and Devices section stay.

## [0.16.0] - 2026-05-31

### Changed

- **Operational dashboard** — your registered devices now live on the **main
  screen** as operational cards (live status, profile, version, per-device
  **build / flash / boot**), and the **batch** buttons (Build all / Flash all /
  Flash ready / Build & flash) moved there too. A device appears on the main
  screen only once it's been **added and given a profile**, so raw discovery no
  longer duplicates there. The **Devices manager** (the former Devices tab) is
  now purely for discovering, adding, and configuring boards.

## [0.15.0] - 2026-05-31

### Added

- **Health & install integrity (Phase 13)** — a new `/firmware/health` check
  reports whether the host is set up for flashing (the passwordless **sudo**
  rule, the **STM32 DFU udev rule**, and **dfu-util**), shown as a **setup**
  badge with a fix-it tooltip. `deploy/setup-sudoers.sh` now also installs a
  `99-stm32-dfu.rules` udev rule so **DFU flashing works without sudo**. This
  completes the Firmware Upgrade widget's planned phases (1–13).

## [0.14.0] - 2026-05-31

### Added

- **Backup & restore (Phase 12)** — **export** the device registry + every
  Kconfig profile as a single portable ZIP, and **import** it back. Firmware
  binaries are excluded (they rebuild from the profiles), and restore is hardened
  against zip path-traversal (only `devices.json` + validated profile names are
  written). Export / import live in the Devices view.

## [0.13.0] - 2026-05-31

### Added

- **Beacon (Phase 11)** — FilaMind now detects connected **Beacon eddy-current
  probes** and updates their firmware through the Beacon plugin's own
  `update_firmware.py` (located via Moonraker's update_manager). The widget shows
  each probe with its revision, the version available in the plugin checkout, and
  a **flash** button — and only appears when a probe is present.

## [0.12.0] - 2026-05-31

### Added

- **Advanced flash (Phase 10)** — sturdier flashing for more boards: DFU now
  **retries** (up to 3×) and **exits via `:leave`** to return to firmware; a
  **USB-to-CAN bridge** (a CAN board that enumerates as a serial path) is flashed
  over serial automatically; a serial board that **re-enumerates** under a new
  `/dev` id after flashing is matched and its registry entry updated; and a board
  can be rebooted straight into **STM32 DFU** with a 1200-baud touch (a new
  **dfu** button beside **boot**).

## [0.11.0] - 2026-05-31

### Added

- **Live status & services (Phase 9)** — the widget now **auto-refreshes**
  every few seconds, so each board's live mode (service / ready / dfu / offline)
  stays current. A new **Services** bar lists the host's Klipper / Moonraker
  units and can **start / stop / restart** them all (ordered so host MCUs come
  up first and go down last). Each saved board gains a live-mode badge and a
  **boot** button that reboots it into its Katapult bootloader.

## [0.10.0] - 2026-05-31

### Added

- **Batch operations (Phase 8)** — build and/or flash every device in one go:
  **Build all**, **Flash all**, **Flash ready** (only boards already sitting in
  a bootloader), and **Build & flash**. It runs as a cancellable background task
  with a live, colorized log; **cancel** stops it at the next checkpoint. Builds
  are de-duplicated by profile, `exclude_from_batch` devices are skipped, and
  each flash reuses the same guarded single-board sequence (print-lock, sudo,
  bootloader reboot, version recording).

## [0.9.1] - 2026-05-31

### Changed

- Settled the Phase 7 registry's public surface on **Devices**: the
  `/api/firmware/devices` (+ `/devices/attach`) endpoints and the `devices.json`
  store. Anyone who integrated against the v0.9.0 paths should update them.

## [0.9.0] - 2026-05-31

### Added

- **Devices (Phase 7)** — FilaMind now keeps a saved device registry
  (`devices.json`): each board remembers its build profile, how it is flashed
  (method, baudrate, CAN interface), free-form notes, an exclude-from-batch
  flag, an optional custom make command, and the separate Katapult / DFU
  **bootloader identity** it takes on while flashing. A new **Devices** view
  lists registered boards (editable inline), **adds** a discovered board, and
  **attaches** a found bootloader device to an existing entry. Board discovery
  now flags which boards are already `managed`.

## [0.8.0] - 2026-05-31

### Added

- **Firmware version tracking (Phase 6)** — FilaMind now captures the Klipper
  version / commit / date a profile is built with (`<profile>.build_info.json`
  via `get_klipper_version`) and records what it flashes to each board
  (`flashed.json`). The **Linux host MCU** and other boards now show their
  firmware version even when Moonraker can't report it (e.g. an unconfigured
  host MCU) — and each profile carries its `built_version`. Closes the
  host-MCU version-display gap.

## [0.7.1] - 2026-05-31

### Changed

- The **Linux host MCU** flash now matches the standard install: stop
  `klipper-mcu`, free the binary with `fuser -k`, install it executable, restart
  the service, and wait for it to come up — warning (instead of leaving it
  silently broken) if the kernel blocks realtime, in which case the `-r` flag
  should be dropped from the klipper-mcu unit. `setup-sudoers.sh` now also grants
  `fuser`.

## [0.7.0] - 2026-05-31

### Added

- **Live MCU telemetry** in the firmware status — each MCU now shows its actual
  clock frequency, awake load, and retransmitted-bytes count (the key host↔MCU
  comms-health signal, highlighted when non-zero), pulled from the MCU's
  `last_stats`. First of the Firmware Upgrade widget's planned enhancements.

## [0.6.2] - 2026-05-31

### Fixed

- The flash readiness probe ran `sudo -n true`, which never matches the narrow
  sudoers rule, so flashing kept reporting "blocked" even after running
  `setup-sudoers.sh`. It now probes an allowed command (`systemctl --version`).

## [0.6.1] - 2026-05-31

### Added

- `deploy/setup-sudoers.sh` — grants the backend the narrow passwordless-sudo
  rights flashing needs (`systemctl`, `dfu-util`, `cp`, `chmod`). Run once with
  sudo to enable the Flash phase; until then the UI reports flashing as blocked
  and points to this script.

### Fixed

- Flash now stops/starts the correct service (`klipper-mcu` for a Linux-process
  MCU, `klipper` for hardware MCUs) and marks an installed Linux MCU binary
  executable.

## [0.6.0] - 2026-05-31

### Added

- **Firmware flash (Phase 5 — Flash)**: push a built artifact onto a board from
  the browser. `POST /api/firmware/flash` runs the right tool for the board —
  Katapult `flashtool.py` (serial / CAN), `dfu-util` (DFU), or `make flash`
  (AVR) — rebooting it to its bootloader first, and streams the log. A read-only
  `POST /api/firmware/flash-plan` previews the exact command + safety gates.
  Flashing is **refused while a print is running**, requires a built artifact,
  and needs passwordless sudo; the UI shows the plan, warnings, and a hard
  confirmation before anything touches the board. Completes the widget's
  configure → build → flash pipeline.

## [0.5.0] - 2026-05-31

### Added

- **Firmware build (Phase 4 — Build)**: compile a saved profile into a flashable
  artifact from the browser. `GET /api/firmware/build/{profile}` stages the
  profile's `.config`, runs `make clean` + `make olddefconfig` + `make`, and
  **streams the build log live** (with stall / total timeouts); the resulting
  `out/klipper.{bin,uf2,elf}` is copied into the artifacts directory under the
  profile name. The Configure view gains a **build** button per profile, a live
  log console, and a **built ✓** indicator.

## [0.4.0] - 2026-05-31

### Added

- **Firmware config editor (Phase 3 — Configure)**: edit Klipper's
  `make menuconfig` options from the browser. The backend loads Klipper's bundled
  `kconfiglib`, serialises `src/Kconfig` into a live menu tree (dependencies
  re-evaluate as values change), and writes a `.config`. Edits are saved as
  **per-board profiles** (one `.config` each) under the FilaMind data dir, with
  list / save / delete via `GET`/`POST`/`DELETE /api/firmware/config/...`. The
  widget gains a **Configure firmware** view that renders the tree as a form with
  a profile selector. Adds a `kconfiglib` dependency (Klipper's own copy is
  preferred at runtime).

## [0.3.0] - 2026-05-31

### Added

- **Board discovery** (`GET /api/firmware/boards`) — finds every flashable MCU on
  any printer by merging four independent sources: configured `[mcu]` sections
  from Moonraker, USB/serial (`/dev/serial/by-id` + ttyACM/ttyUSB), CAN (Katapult
  `flashtool.py -q` on each CAN interface), and DFU (`dfu-util -l`). Each board
  reports its connection (usb/can/dfu/linux), mode (service / ready / dfu),
  whether it is configured, and its running firmware version. Surfaced as a
  **Detected boards** section in the Firmware Upgrade widget.

## [0.2.2] - 2026-05-31

### Added

- Firmware Upgrade widget now surfaces the optional **Linux host MCU** (Klipper
  "Linux process" MCU) explicitly — `active` / `available · not configured` /
  `not installed` — based on the host's `klipper-mcu` service and whether a host
  MCU is wired into the running config. Each MCU row also shows its connection
  kind (host / canbus / usb / serial).

## [0.2.1] - 2026-05-31

### Changed

- Firmware Upgrade widget: the **host** is now shown as a first-class row in the
  device list — the reference version every MCU is compared against — styled
  distinctly instead of a separate header line.

## [0.2.0] - 2026-05-31

### Added

- **Firmware Upgrade widget — Phase 1**: read-only firmware status showing each
  MCU's version, host↔MCU sync detection, and toolchain readiness
  (`GET /api/firmware/status`). The first FilaMind widget.
- A living [`ROADMAP.md`](ROADMAP.md).
- Dev test harness (`dev/virtual-printer/`): develop against any Moonraker through
  the Vite dev proxy via `MOONRAKER_PROXY_TARGET` (strips the browser Origin, so no
  printer CORS changes are needed) — plus an optional Docker simulated printer.
- Verified the full on-device deployment on a real **BigTreeTech CB1**: backend
  systemd service + nginx-served UI + a **FilaMind Flow entry in the Mainsail
  sidebar**, with klippy `ready` and a live Connected badge.

### Changed

- The frontend now defaults to **same-origin** endpoints (it is served behind a
  proxy that forwards Moonraker/backend traffic) instead of `host:7125`, so no host
  or port is baked into the build and there is no CORS.
- The deploy nginx template strips `Origin` on the Moonraker proxy.
- Relicensed from MIT to **GPL-3.0-or-later** to match the Klipper / Moonraker ecosystem.
- Header now has a **Back to Mainsail** button.

### Fixed

- Backend `cors_origins` raised a `SettingsError` when set from the environment; it
  is now a comma-separated string exposed as `cors_origin_list`.

## [0.1.0] - 2026-05-31

### Added

- Project scaffold (empty, no feature widgets yet).
- Frontend: Vue 3 + Vite + TypeScript + Tailwind CSS with a Neo-Brutalist design
  system (tokens + `nb-card` / `nb-btn` / `nb-badge` components).
- `MoonrakerClient`: reconnecting JSON-RPC WebSocket client with request
  correlation, notification fan-out, and automatic subscription restoration.
- Widget registry (extensibility core) + Pinia printer store + app shell
  (sidebar, header, live connection status, empty-state dashboard).
- Backend: FastAPI service with health and Moonraker reachability endpoints,
  settings via `pydantic-settings`, and a server-side Moonraker HTTP client.
- Tooling: ESLint (flat) + Prettier + Vitest; Ruff + Mypy + Pytest; GitHub
  Actions CI; deployment templates (systemd, nginx, Moonraker update_manager,
  Mainsail navi).

[Unreleased]: https://github.com/filamind-app/filamind-flow/compare/v0.24.1...HEAD
[0.24.1]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.24.1
[0.24.0]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.24.0
[0.23.1]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.23.1
[0.23.0]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.23.0
[0.22.0]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.22.0
[0.21.2]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.21.2
[0.21.1]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.21.1
[0.21.0]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.21.0
[0.20.1]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.20.1
[0.20.0]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.20.0
[0.19.0]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.19.0
[0.18.1]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.18.1
[0.18.0]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.18.0
[0.17.1]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.17.1
[0.17.0]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.17.0
[0.16.2]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.16.2
[0.16.1]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.16.1
[0.16.0]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.16.0
[0.15.0]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.15.0
[0.14.0]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.14.0
[0.13.0]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.13.0
[0.12.0]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.12.0
[0.11.0]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.11.0
[0.10.0]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.10.0
[0.9.1]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.9.1
[0.9.0]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.9.0
[0.8.0]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.8.0
[0.7.1]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.7.1
[0.7.0]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.7.0
[0.6.2]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.6.2
[0.6.1]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.6.1
[0.6.0]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.6.0
[0.5.0]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.5.0
[0.4.0]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.4.0
[0.3.0]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.3.0
[0.2.2]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.2.2
[0.2.1]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.2.1
[0.2.0]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.2.0
[0.1.0]: https://github.com/filamind-app/filamind-flow/releases/tag/v0.1.0
