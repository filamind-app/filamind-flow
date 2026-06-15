# Macro Designer

Macro Designer is an offline G-code simulator. You write or paste a program, and it shows you the toolhead path, the numbers behind the move, and a plain-language walkthrough of what each command does. Nothing is sent to the printer, so it is a safe place to draft and check a macro before you ever run it. It helps if you are writing a new macro, trying to understand one you inherited, or just want to see what your START_PRINT actually does.

## What it does

At its core, the widget draws your program. Type out a sequence of moves and it renders the toolhead path in 2D, along with the bounding box, total travel and extrusion, an accel-aware time estimate, and a per-command timeline. The path can be recoloured as a speed or extrusion-rate heatmap when you want to see where things slow down or where the extruder is working hardest.

It understands the real macro template language, not just plain G-code. Expressions written as `{ ... }`, along with `{% for %}` and `{% if %}` control flow, are rendered in a sandbox. Loops and conditionals expand the same way they would on the printer, so a macro that repeats a move ten times draws ten moves.

The simulation is grounded in your own machine. The preview uses your printer's real build area and speed cap, and any move that leaves the bed or exceeds `max_velocity` is drawn in red. You can also import a macro you already have installed: pick a `[gcode_macro]` from the printer, and its real body loads and dry-runs, with its parameters discovered into editable fields you can change.

A few tools help you read and check the result. The Explain-this-macro walkthrough narrates each command in plain language, showing the running mode and the cumulative totals as it goes, and it stays hover-synced with the path so you can point at a line and see where it is on the bed. A static linter catches common macro-logic foot-guns such as an unbalanced SAVE/RESTORE_GCODE_STATE pair, a macro that ends in relative mode, or an extrude before the axes are homed. And A/B compare runs a second program alongside the first and diffs the two, which is useful when you are weighing a change.

Beyond inspection, the widget can generate a START_PRINT and END_PRINT pair tailored to your printer. It takes into account the kinematics, the build area, the leveling method the machine has, and whether there is a heated bed. You can then append both to a config file. A built-in macro reference library and illustrated help are there when you need a refresher.

## Using it

A typical session looks like this:

1. Start with a program. Write or paste G-code into the editor, or import one of your printer's installed `[gcode_macro]` definitions and let its body load.
2. If you imported a macro that takes parameters, fill in the editable fields that were discovered from it.
3. Read the simulation. Check the path, the bounding box, the travel and extrusion totals, and the time estimate. Watch for anything drawn in red, which means a move left the bed or went over the speed cap.
4. Switch the path to the speed or extrusion-rate heatmap if you want a closer look at pacing.
5. Open the Explain-this-macro walkthrough to step through each command, and hover lines to find them on the path.
6. Check the linter for logic problems like an unbalanced state save/restore or an extrude before home.
7. If you are comparing two versions, load the second into A/B compare and look at the diff.
8. To build print macros, generate a START_PRINT / END_PRINT pair for your printer and append them to a config file when you are happy with them.

## Notes

The simulator is offline. It never sends anything to the printer, which is the whole point: you can experiment freely without touching the machine.

The one action that does write to your config is appending a generated START_PRINT / END_PRINT pair. That goes through the same confirm gate used elsewhere in FilaMind Flow. A backup is taken first, and the write is refused while a print is running.

The preview is only as accurate as the machine values behind it. Out-of-bounds and over-speed moves are flagged against your real build area and `max_velocity`, and the time estimate is accel-aware, but a simulation is still an estimate and not a guarantee of how the real motion will play out.

This works on any Klipper printer, since it reads your kinematics, build area, speed cap, leveling, and bed configuration to ground the simulation and to tailor the generated macros.

← [All widgets](./README.md) · [FilaMind Flow](../../README.md)
