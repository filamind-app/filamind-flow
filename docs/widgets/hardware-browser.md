# Hardware Browser

The Hardware Browser is a curated reference of 3D-printing hardware. It pulls a large pile of overlapping part data into clean, canonical entities, and for each one it gives you the full spec sheet plus a copy-ready Klipper config. If you are wiring up a new board, picking a motor, or just trying to remember which driver a part uses, this is where you look it up.

## What it does

At its core the browser holds more than 2,600 deduplicated parts. "Deduplicated" matters here. The same board or motor often shows up under several names across vendors and forums, and the browser collapses those into a single canonical entity so you are not sifting through near-identical duplicates.

The biggest categories each come with their own detail view:

- **Boards (380).** Every board carries an aggregated pin map and port list, alongside a copy-ready pin config you can drop straight into your printer setup.
- **Drivers (55).** For the TMC family you get the `[tmcXXXX]` config block. Standalone parts get honest notes instead, because there isn't a meaningful config block to hand you.
- **Motors (670+).** Each motor includes a recommended `run_current` and a config snippet. Where the data exists, you also see real OEM part ranges rather than a single guessed value.
- **Hosts (220).** This covers SBCs and x86 machines, each with an `[mcu host]` block.

Beyond those four, there is a generic catalog covering nine more categories: sensors and probes, hotends, extruders, fans / power / bed, cameras and displays, motion, nozzles, filament, and electronics. You can also browse by **Brand** and by **MCU**, which is handy when you want to start from a manufacturer or a chip rather than from a specific part.

Everything is cross-linked. Open a board and you'll see clickable chips that jump to its manufacturer, its MCU, or the drivers it uses. Following those links is usually faster than searching again, and it makes it easy to understand how a part fits into the rest of a build.

Search works across name, manufacturer, and spec, so you can find a part however you happen to remember it. The same data layer behind the browser is what other FilaMind Flow widgets link to, which is why a part you look up here lines up with what those widgets show. Throughout, the help is illustrated rather than wall-of-text.

## Using it

A typical session looks like this:

1. Pick a category, or use a Brand or MCU view, to narrow down where you're looking.
2. Search by name, manufacturer, or spec to find the exact part.
3. Open the part to read its full spec sheet.
4. Copy the Klipper config. For a board that's the pin config, for a TMC driver it's the `[tmcXXXX]` block, for a motor it's the snippet with a recommended `run_current`, and for a host it's the `[mcu host]` block.
5. Follow the cross-link chips to jump to the related manufacturer, MCU, or drivers when you want more context.

## Notes

The configs and specs here work on any Klipper printer. Nothing in the browser is tied to a particular machine.

The browser is a reference. It shows you data and hands you config text to copy, but it does not write to your printer or change your setup on its own. You stay in control of what actually goes into your config.

A couple of honesty caveats are baked into the data itself. Standalone drivers carry plain notes instead of a config block, because there isn't a real one to give. And the OEM part ranges on motors only appear where that information genuinely exists, so you won't see invented numbers filling the gaps.

← [All widgets](./README.md) · [FilaMind Flow](../../README.md)
