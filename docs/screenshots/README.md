# Screenshots

Real screenshots from a Sovol SV08 (CoreXY) running FilaMind Flow, with live data
from the printer and its host. Shown in the default light theme and English; the UI
also ships in 7 languages and 7 themes.

## Dashboard

The home view: live printer and host state, a short getting-started checklist, and
quick cards into each tool.

![FilaMind Flow dashboard](dashboard.png)

## Machine Doctor

One read-only scan across the whole printer, graded A-F, with every finding linking
to the widget that fixes it.

![Machine Doctor](machine-doctor.png)

[Read more](../widgets/machine-doctor.md)

## Firmware Manager

MCU firmware versions, host sync status, toolchain readiness, and a gated build/flash
for every board.

![Firmware Manager](firmware-manager.png)

[Read more](../widgets/firmware-manager.md)

## Motor Drivers

Live TMC stepper-driver inventory with datasheet-based current tuning, homing, and a
guarded register editor.

![Motor Drivers](motor-drivers.png)

[Read more](../widgets/motor-drivers.md)

## Hardware Browser

A curated, deduped catalog of thousands of parts, with the parts detected on this
printer surfaced at the top.

![Hardware Browser](hardware-browser.png)

[Read more](../widgets/hardware-browser.md)

## Config Editor

The live Klipper config read from Moonraker, parsed into sections and parameters, with
structural problems flagged.

![Config Editor](config-editor.png)

[Read more](../widgets/config-editor.md)

## Board Topology

An interactive map of the printer's control boards and the MCUs they talk to, linked to
the hardware catalog.

![Board Topology](board-topology.png)

[Read more](../widgets/board-topology.md)

## Max-Flow

Ramp extrusion flow to find the highest volumetric speed the hotend can sustain, watched
by the extruder's StallGuard load.

![Max-Flow](max-flow.png)

[Read more](../widgets/max-flow.md)

## Input Shaping

Turn a resonance capture into a ready `[input_shaper]` config, with a guided walk-through
from noise to shaper.

![Input Shaping](input-shaping.png)

[Read more](../widgets/input-shaping.md)

## Macro Designer

An offline G-code simulator: paste or load a macro and see its toolhead path, totals, and
a time estimate without touching the printer.

![Macro Designer](macro-designer.png)

[Read more](../widgets/macro-designer.md)

## Config Templates

Paste-ready Klipper config blocks and macros, filterable by category, with one-click copy.

![Config Templates](config-templates.png)

[Read more](../widgets/config-templates.md)

## KlipperScreen Studio

Manage the printer's touchscreen: edit its config safely, build themes and menus, or run
Kiosk mode.

![KlipperScreen Studio](klipperscreen-studio.png)

[Read more](../widgets/klipperscreen-studio.md)

## Host Control

Monitor the printer's Linux host (CPU, memory, disk, uptime), manage its services, free
space, and change system settings.

![Host Control](host-control.png)

---

Back to the [main README](../../README.md) or the [widget docs](../widgets/).
