# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
