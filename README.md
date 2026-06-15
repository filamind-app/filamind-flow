<div align="center">

# FilaMind Flow

A control panel for Klipper and Moonraker that lives next to Mainsail and Fluidd.
It grows one widget at a time, and each one earns its place by being genuinely useful.

**Built by Egyptian makers, for world makers. Happy printing.** 🇪🇬

[![Support on Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/I2I119XEIV)

[![CI](https://github.com/filamind-app/filamind-flow/actions/workflows/ci.yml/badge.svg)](https://github.com/filamind-app/filamind-flow/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/filamind-app/filamind-flow?color=111111&label=release&sort=semver)](https://github.com/filamind-app/filamind-flow/releases/latest)
[![License: GPLv3](https://img.shields.io/badge/License-GPLv3-111111.svg)](LICENSE)
[![Last commit](https://img.shields.io/github/last-commit/filamind-app/filamind-flow?color=111111&label=updated)](https://github.com/filamind-app/filamind-flow/commits/main)

[![Klipper](https://img.shields.io/badge/Klipper-compatible-111111)](https://www.klipper3d.org)
[![Moonraker](https://img.shields.io/badge/Moonraker-API-111111)](https://moonraker.readthedocs.io)
[![Mainsail](https://img.shields.io/badge/Mainsail-sidebar-111111)](https://docs.mainsail.xyz)
[![Fluidd](https://img.shields.io/badge/Fluidd-ready-111111)](https://docs.fluidd.xyz)

[![Vue.js](https://img.shields.io/badge/Vue.js-3-4FC08D?logo=vuedotjs&logoColor=white)](https://vuejs.org)
[![Vite](https://img.shields.io/badge/Vite-6-646CFF?logo=vite&logoColor=white)](https://vite.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-06B6D4?logo=tailwindcss&logoColor=white)](https://tailwindcss.com)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org)

[Install](#install) · [Uninstall](#uninstall) · [Widgets](#widgets) · [Docs](#documentation) · [Support](#support)

</div>

FilaMind Flow is a standalone single-page app that talks directly to Moonraker over REST and a WebSocket. It is a static frontend plus a small FastAPI backend, so it sits beside Mainsail and Fluidd rather than replacing them. The browser does most of the work, which keeps it light on the printer host, and the project grows one widget at a time.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/filamind-app/filamind-flow/main/scripts/install.sh | bash
```

This installs the backend service, serves the prebuilt UI through nginx on port 8090, and registers with Moonraker so updates are one click away. It also adds a sidebar link, and you can re-run it any time to update or repair the install.

## Uninstall

```bash
bash scripts/install.sh uninstall
```

This removes the service, the nginx site, the sidebar entry, the Moonraker registration, and the sudo and udev rules, while leaving the app files in place.

## Widgets

| Widget | What it does | Status |
| ------ | ------------ | ------ |
| [Machine Doctor](docs/widgets/machine-doctor.md) | One read-only health scan, graded A-F, each finding linking to its fix | ✅ Shipped |
| [Firmware Manager](docs/widgets/firmware-manager.md) | Build and flash Klipper firmware on every MCU, guided and gated | ✅ Shipped |
| [Input Shaping](docs/widgets/input-shaping.md) | Turn a resonance capture into a ready [input_shaper] config | ✅ Shipped |
| [Config Editor](docs/widgets/config-editor.md) | Browse, edit, and safely save your printer's Klipper config with hardware-aware checks | ✅ Shipped |
| [Max-Flow](docs/widgets/max-flow.md) | Ramp extrusion flow to find your hotend's safe max volumetric speed | ✅ Shipped |
| [Board Topology](docs/widgets/board-topology.md) | Interactive map of your printer's control boards, linked to the hardware catalog | ✅ Shipped |
| [Macro Designer](docs/widgets/macro-designer.md) | Offline G-code simulator: draw, explain, lint, and compare macros safely | ✅ Shipped |
| [Hardware Browser](docs/widgets/hardware-browser.md) | Curated, deduped catalog of 2,600+ parts with copy-ready Klipper configs | ✅ Shipped |
| [Config Templates](docs/widgets/config-templates.md) | Paste-ready Klipper config blocks and macros, filterable by category with one-click copy | ✅ Shipped |
| [Motor Drivers](docs/widgets/motor-drivers.md) | Live TMC driver inventory with datasheet-based current tuning, homing, and register editing | ✅ Shipped |
| [KlipperScreen Studio](docs/widgets/klipperscreen-studio.md) | Manage the printer's touchscreen: edit config, build themes and menus, or run Kiosk mode | ✅ Shipped |

Every widget has its own page under [docs/widgets/](docs/widgets/).

## Proven on real printers

FilaMind Flow is validated on two machines that disagree on almost everything that matters to a control panel. The first is a Sovol SV08: an STM32F103 mainboard, TMC2209 drivers over UART, a USB toolhead, and a BTT CB1 host. The second is a Voron-class CoreXY: an STM32H723 mainboard, six TMC5160 drivers on a shared software-SPI bus, a CAN toolhead, and a Raspberry Pi 4. Bringing the second printer online hunted the "works on my printer" class of bug. Each one it surfaced became a generic fix rather than a special case.

## How it's built

The frontend is a Vue 3 and Vite single-page app, and a small FastAPI backend handles anything that has to run server-side. State flows through one reconnecting Moonraker WebSocket, mirrored into a shared store every widget reads from. Adding a feature means registering a widget; the core does not change. The UI ships in 7 languages, including right-to-left Arabic, with 7 switchable themes. For the full picture, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Develop

See [CONTRIBUTING.md](CONTRIBUTING.md) for local setup, the dev workflow, and how to add a widget.

## Documentation

| Document | What's inside |
| -------- | ------------- |
| [ROADMAP.md](ROADMAP.md) | Phase-by-phase plan and status for every widget |
| [CHANGELOG.md](CHANGELOG.md) | Release history |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Dev workflow, conventions, and how to add a widget |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Design and data-flow deep dive |
| [backend/README.md](backend/README.md) | Backend service, `/api` endpoints, and `FILAMIND_*` settings |
| [docs/widgets/](docs/widgets/) | One page per widget |

## Support

FilaMind Flow is free and open source, built and maintained in spare time. If it saved you a tuning session, or you just want to see it grow, a coffee helps keep the work going. Code, data, and ideas are just as welcome.

<div align="center">

[![Support on Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/I2I119XEIV)

</div>

## Credits

Built and maintained by the DeltaFabs team:

- abdelmonem awad — <eg2@live.com>
- Ahmed bebars — <Ahmedbebars1@gmail.com>

## License

[GPL-3.0-or-later](LICENSE) © 2026 DeltaFabs team.
