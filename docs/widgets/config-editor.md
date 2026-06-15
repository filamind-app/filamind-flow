# Config Editor

A place to read and change your printer's Klipper configuration without leaving FilaMind Flow. It is meant for anyone who edits `printer.cfg` by hand today and wants the same control with a few more guardrails: backups, validation, and hardware-aware help.

## What it does

### Browse the live config

The editor pulls your configuration straight from Moonraker, so you are always looking at what the printer is actually running. Every `.cfg` and `.conf` file is parsed into its `[sections]`, and each parameter keeps its value and its inline comment. Multi-line values stay intact. The auto-generated `SAVE_CONFIG` block is flagged so you can tell hand-written settings from ones Klipper wrote back. A file picker lets you move between included files.

You can read the config two ways. The structured view groups everything by section. The raw view shows the file text as-is. If there is a structural problem in the config, a validation banner surfaces it instead of letting it hide until the next restart.

### Edit and save safely

Editing happens in the raw view, and saving goes through a confirm gate. Before any write, the editor takes an automatic timestamped backup. Writes are refused while the printer is printing. Once a change is saved you can apply it with a one-click `FIRMWARE_RESTART`.

### Structured-view inline editing

You don't have to drop to raw text for common edits. In the structured view, `[tmcXXXX]` register fields render with the right control and the silicon-fact range for that register, so you can see what values are actually valid. Every `*_pin` field offers the named pins from its board as type-ahead suggestions, with inline flags when a pin is off-board, already used elsewhere, or carries an electronics caveat.

### Insert blocks from the catalog

When you need to add hardware, you can insert a config block from the catalog rather than typing it from memory. Pick a driver, motor, or board and the editor appends its real `[tmcXXXX]` or pin-map block for review, with correct `run_current`, `sense_resistor`, and pin names already filled in.

### Catch problems before they bite

Several checks run against the whole config. The Pin Doctor scans for double-assigned pins and warns about driving mains on a logic-level pin. Driver value sanity cross-checks each TMC driver's `run_current` and `microsteps` against both the driver's own ceiling and the rating of the motor assigned to it. These run across the config, not just the section you happen to be looking at.

### Reconcile disk vs. live

Klipper holds some values in memory that differ from what is on disk. The drift healer shows you which values you edited but never restarted, plus anything still pending in `SAVE_CONFIG`. For each parameter you can adopt the live value with one click.

### Work across files

The project view treats your config as the multi-file setup it usually is. It draws the `[include]` dependency tree, lets you search across the whole project, and runs a cross-file lint. The lint catches broken includes, an orphan TMC driver with no matching stepper, and override visibility, so you can see when one file's value is quietly replaced by another's.

### Inline knowledge

Each section carries a short plain-language blurb explaining what it is for. A driver section deep-links to its catalog entity in the Hardware Browser when you want the full part details.

### Backup timeline

Every pre-save snapshot is kept and browsable. You can diff any snapshot against your current draft to see exactly what changed, and restore one if you need to. Restoring goes through the same confirm gate and backup as a normal save.

## Using it

1. Open the Config Editor and pick a file from the file picker. The structured view loads the live config; check the validation banner for anything flagged.
2. Make your change. Edit register and pin fields inline in the structured view, or switch to the raw view for free-form edits. To add hardware, insert a driver, motor, or board block from the catalog and adjust it.
3. Look over the checks. The Pin Doctor, driver value sanity, and cross-file lint will point out conflicts or out-of-range settings.
4. If live values have drifted from disk, use the drift healer to adopt the ones you want.
5. Save. Confirm the write, and the editor takes a timestamped backup first.
6. Apply the change with `FIRMWARE_RESTART`.
7. Later, use the backup timeline to diff or restore an earlier snapshot if needed.

## Notes

Saving always passes through a confirm gate, and an automatic timestamped backup is taken before any write. Writes are refused while the printer is printing, so finish or stop the job first. Restoring from the backup timeline uses the same gate and backup as a normal save.

The pin range data and register controls reflect known silicon facts, and the sanity checks compare against driver ceilings and motor ratings. They are there to catch obvious mistakes, not to replace reading your hardware's datasheet. The editor works on any Klipper printer, since it reads and parses whatever config Moonraker reports rather than assuming a specific machine.

← [All widgets](./README.md) · [FilaMind Flow](../../README.md)
