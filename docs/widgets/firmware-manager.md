# Firmware Manager

Build and flash Klipper firmware on every MCU your printer has, without the SSH
session and the half-remembered commands. It is meant for anyone who has ever
stared at a `make menuconfig` screen and wished for a map: first-time board
owners, people adding a CAN toolhead, and seasoned users who just want the flash
done right.

## What it does

The widget is organized into tabs so you can find the right job quickly: Guided,
Status, Configure, Devices, and External.

**Build configuration.** Each MCU gets its own Kconfig profile, so the settings
for your mainboard and your toolhead stay separate and don't overwrite each
other. A live web editor lets you set the build options in the browser. There is
no need to drop to a terminal to run `menuconfig`.

**Flashing.** When the firmware is built, the widget can flash it over the three
methods Klipper hardware actually uses: Katapult, DFU, and SD card. Whichever one
applies to your board, the flow is the same. Before anything is written, you get a
flash-plan preview that spells out what will happen, and you have to confirm it.
Nothing is flashed until you say so.

**A guided walkthrough for new boards.** The Guided tab takes a new board from
nothing to flashed firmware in order, so you are never guessing which step comes
next. It is the place to start if you are setting up a board for the first time.

**Beacon probe updates.** If you run a Beacon probe, its firmware can be updated
from here too, alongside your other MCUs.

**Host and update awareness.** The widget can control the host's Klipper service,
which is the part that has to stop and restart around a flash. It also raises
host-to-MCU update alerts, so when the host's Klipper version moves ahead of what
an MCU is running, you find out instead of hitting a mismatch mid-print.

**Inspecting firmware you didn't build here.** The External tab has a firmware
inspector and a diff. You can look at an external firmware file and compare it,
which is useful for checking what a prebuilt or vendor-supplied image actually
contains before you trust it.

**Help that stays close.** There is a glossary, illustrated help, and a
build-to-flash guide built into the widget, so the explanation for a term or a
step is one click away rather than in a separate wiki.

## Using it

A typical first run looks like this:

1. Open the **Guided** tab and follow the new-board walkthrough. It orders the
   steps for you.
2. In **Configure**, set the Kconfig profile for the MCU you are working on. Each
   board has its own profile, so pick the right one.
3. Build the firmware using the settings you chose.
4. Move to **Devices** and choose how to flash, Katapult, DFU, or SD card,
   depending on the board.
5. Read the flash-plan preview, then confirm. The flash runs only after you
   approve the plan.
6. Use **Status** to keep an eye on your MCUs and watch for host-to-MCU update
   alerts over time. When the host gets ahead of an MCU, come back and reflash.

For firmware that came from somewhere else, skip the build and open the
**External** tab to inspect and diff the file first.

## Notes

- Every flash sits behind a flash-plan preview and a confirm gate. You always see
  the plan before anything is written.
- Kconfig profiles are per board. The settings for one MCU do not leak into
  another.
- The External firmware inspector and diff are there to help you check images you
  did not build in the widget, before flashing them.
- Updating the host's Klipper service and flashing MCUs are coordinated, and the
  host-to-MCU alerts are meant to keep the two from drifting apart.
- The widget works on any Klipper printer.

← [All widgets](./README.md) · [FilaMind Flow](../../README.md)
