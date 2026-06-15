# KlipperScreen Studio

KlipperScreen Studio lets you manage the printer's physical touchscreen without dropping to the command line. It's for anyone who wants to retheme that screen, rearrange its menus, or change how it behaves, and would rather not hand-edit `KlipperScreen.conf` over SSH.

## What it does

At its core the widget gives you control over `KlipperScreen.conf`. You can edit it directly in a raw view, or use a Settings form that covers the common `[main]` options. The form handles theme, language, screen sleep, font size, the 24-hour clock, DPMS, the cursor, and the e-stop confirmation. It only writes the values you actually change, so the rest of your file is left alone. Either way, edits go through the same gated save as the rest of FilaMind Flow: a backup is taken first, the save is refused while the printer is busy, and a stale-write guard stops you overwriting a file that changed underneath you. When you're ready, one click restarts KlipperScreen so your changes take effect.

If you'd rather design the screen visually than think in config keys, there are two tools for that. The theme builder lets you pick a color for each palette token and set the corner radius, with a live preview as you go. When you're happy, it writes a real theme to the screen. The visual menu editor handles layout. It shows each screen's button grids, including `__main`, `__print`, and `__splashscreen`, as a tree you can add to, rename, reorder, and nest. Every button does one of three things: it opens a sub-menu, opens a screen, or runs G-code.

There's also a Kiosk mode for people who want to go all the way. It turns the touchscreen into FilaMind Flow itself, running as a fullscreen browser in place of KlipperScreen. The swap is reversible and temporary by default, with an option to make it the default instead. If the screen ends up dark, it auto-recovers. Kiosk mode is set up once with `scripts/install.sh kiosk`.

A glossary and per-tab illustrated help are built in, so you can read what a setting or tab does without leaving the widget.

## Using it

A typical session looks like this:

1. Open KlipperScreen Studio on the printer host.
2. Pick how you want to work. Use the Settings form for the common `[main]` options, the raw editor for anything else, or the theme and menu builders to design the screen visually.
3. Make your changes. The form writes only what you touch; the theme builder shows a live preview before it commits.
4. Save. The change is backed up first and goes through the gated save.
5. Restart KlipperScreen with one click so the new config or theme loads.

If you want the touchscreen to show FilaMind Flow instead of KlipperScreen, install Kiosk mode once with `scripts/install.sh kiosk`, then switch it on. It's temporary unless you choose to make it the default, and you can switch back.

## Notes

Every save is gated. A backup is written before any change, saves are refused while the printer is busy, and the stale-write guard protects against overwriting a file that was modified since you loaded it. Nothing is applied to the screen until you restart KlipperScreen.

The Settings form deliberately writes only the keys you change, so it won't reformat or strip the rest of your `KlipperScreen.conf`. For options the form doesn't cover, use the raw editor.

Kiosk mode replaces KlipperScreen on the touchscreen with FilaMind Flow. The swap is reversible and defaults to temporary, and it auto-recovers a dark screen, but it does need the one-time `scripts/install.sh kiosk` setup before you can use it.

The widget runs on the printer host. It works with KlipperScreen on any Klipper printer.

← [All widgets](./README.md) · [FilaMind Flow](../../README.md)
