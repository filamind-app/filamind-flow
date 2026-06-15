# Max-Flow

Max-Flow finds the highest volumetric flow rate your hotend can actually sustain, in mm3/s. It pushes the extrusion flow higher and higher until the extruder gear slips, then reports the number you can trust. This is the figure you plug into your slicer as a maximum volumetric speed, so it helps anyone tuning for faster, more reliable prints.

## What it does

The core of the widget is a flow ramp. It increases the commanded extrusion flow step by step and watches for the moment the extruder can no longer keep up. The slip is detected without you having to listen for clicks or eyeball the filament. By default it reads the extruder's TMC StallGuard load, which rises as the motor strains and drops sharply when the gear loses its grip on the filament.

You can choose how the slip is sensed. The Detection method selector offers Auto, StallGuard, and Accelerometer. StallGuard uses the TMC driver's load signal. Accelerometer uses the toolhead accelerometer to pick up the vibration of a slipping gear instead. Auto starts with StallGuard and falls back to the accelerometer if StallGuard can't produce a usable reading. The accelerometer method is experimental.

Before any heating happens, the widget gets the printer ready. It homes the axes and centers the nozzle so you have a clear view of what's going on. If a camera is configured, a small picture-in-picture webcam view is shown. A phase stepper walks through the run so you always know where you are: Home, Center, Heat, Check, then Ramp.

Once the hotend reaches temperature, a StallGuard sanity pre-check runs. It confirms the live load signal is actually usable before the ramp starts. If the signal isn't good enough, the run stops early and tells you why rather than producing a meaningless result.

Some extruder setups need a nudge to make StallGuard readable. For a TMC2209 or TMC2240 extruder running in SpreadCycle, there's an optional auto-StealthChop step. It temporarily writes a `stealthchop_threshold` so the test can run, and comments it back out again when the run is over.

When the ramp finishes, you get the max sustained flow in mm3/s, plus a suggested slicer maximum volumetric speed at 80% and 90% of that figure to leave yourself some margin. The widget also remembers the hotend you picked, so it's prefilled the next time you open it. Illustrated help is built in if you want a refresher on what each part means.

## Using it

1. Pick your hotend to prefill the test. Your choice is remembered across reloads.
2. Preview the ramp. The widget shows you the exact plan, flow rate paired with feedrate for each step, so there are no surprises.
3. Choose a detection method, or leave it on Auto.
4. Work through the safety checklist and confirm the run at the gate.
5. Let the printer home and center the nozzle. Watch the webcam preview if you have a camera, and follow the Home, Center, Heat, Check, Ramp stepper.
6. Wait for the StallGuard sanity pre-check to pass once the hotend is at temperature.
7. The ramp runs and stops at the first slip.
8. Read off the max sustained flow and the suggested 80% / 90% slicer values.

## Notes

A run cannot start without passing the safety checklist and the confirm gate first. The widget also refuses to run while the printer is printing.

Safety is built into how the test ends. The ramp stops at the very first sign of a slip, and the heater is always cut at the end of a run.

The pre-check matters. If StallGuard can't give a usable signal, the run stops early with a clear message instead of carrying on. With Auto detection it will try the accelerometer fallback instead.

The accelerometer (vibration) detection method is experimental. StallGuard is the more proven path where your hardware supports it.

The auto-StealthChop step only applies to a TMC2209 or TMC2240 extruder in SpreadCycle. It's optional, it's temporary, and it leaves your config as it found it by commenting the threshold back out.

← [All widgets](./README.md) · [FilaMind Flow](../../README.md)
