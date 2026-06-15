# Motor Drivers

The Motor Drivers widget gives you a live view of every TMC stepper driver on your printer and the tools to tune them safely. It reads straight from the Klipper config, so it works on any printer without setup, and it's aimed at anyone who wants to dial in run current, homing, and chopper settings without memorizing register names.

## What it does

At its core the widget is a live inventory. It lists every TMC driver Klipper knows about and shows the settings that matter: run and hold current, chopper mode, microsteps, StallGuard, temperature, and overall health. Each driver is annotated with authoritative facts from a built-in capability map, so the numbers come with context about what that particular model actually supports.

Pairing drivers with motors is the other half of the picture. You can assign each axis its motor from a catalog of more than 200 models. Once an axis has a motor, the widget reads the motor's datasheet through a built-in `motor_constants` physics model and recommends a run current along with the matching driver registers. You can copy those values into your config, or apply them live behind a confirmation step. Live changes are reversible, and the widget will refuse to apply them while a print is running.

Homing gets its own panel, and it adapts to how each axis actually homes. If an axis uses a physical endstop switch, you see the live switch state and can run a test home. If it homes sensorless, you get a StallGuard tuner that knows the correct behavior for your specific driver model. Z-probe homing is recognized too, so the panel matches the method rather than showing controls that don't apply.

For deeper work there's an advanced register editor. It edits a safe subset of TMC registers live, guarded by a server-side allowlist and value clamping. Raw current registers and protection registers are blocked outright, so you can't reach the settings that would let you damage hardware.

Rounding things out are a few live and convenience tools. A live monitor tracks temperature, StallGuard load, and faults as they happen. You can sync multi-motor axes so both drivers stay in step. And if you'd rather not drive each panel yourself, a Guided wizard walks you through the whole process. A glossary and illustrated help are available throughout.

## Using it

A typical session looks like this:

1. Open the widget and review the driver inventory. Check current, microsteps, temperature, and health for each axis.
2. Assign each axis its motor from the catalog.
3. Read the recommended run current and registers derived from the motor's datasheet.
4. Copy those values into your config, or apply them live behind the confirm step.
5. Set up homing in the homing panel. Test the switch for switch-homed axes, or tune StallGuard for sensorless ones.
6. Use the advanced register editor only when you need a setting the recommendation doesn't cover.
7. Keep the live monitor open while you test, and sync multi-motor axes if your machine has them.

If you'd prefer a single guided path, start the wizard and let it lead you through the same steps in order.

## Notes

Live changes are gated. Anything that writes to the driver asks you to confirm first, and those changes are reversible. While a print is running, the widget refuses to apply live changes at all.

The advanced register editor is deliberately constrained. It only touches an allowlisted, clamped subset of registers. Raw current and protection registers are off-limits, which keeps the editor from being a way around the safety limits elsewhere in the widget.

The recommendations come from a built-in capability map and a `motor_constants` physics model fed by motor datasheets. They're a strong starting point, but treat them as recommendations rather than final values for every machine.

The widget is generic. It reads its inventory from the Klipper config and works across all printers and TMC driver models, with no per-printer configuration required.

← [All widgets](./README.md) · [FilaMind Flow](../../README.md)
