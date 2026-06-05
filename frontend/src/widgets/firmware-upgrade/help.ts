/** Plain-language help copy for the Firmware Upgrade widget — one source of truth, rendered
 *  by `HelpNote.vue` behind a collapsed "ℹ what's this?" toggle (the project's widget-UX rule).
 */

export type HelpIlloKey = 'mcu' | 'flash' | 'sync' | 'tool'

export type HelpTopic =
  | 'glossary'
  | 'overview'
  | 'guided'
  | 'status'
  | 'toolchain'
  | 'services'
  | 'devices'
  | 'configure'
  | 'external'
  | 'flash'

export interface HelpEntry {
  title: string
  body: string
  illo?: HelpIlloKey
}

export interface GlossaryTerm {
  term: string
  def: string
}

export const GLOSSARY: GlossaryTerm[] = [
  {
    term: 'Klipper firmware',
    def: 'The small program running on each control board that turns the host’s step/dir commands into motion. It must be built from the same Klipper version as the host.',
  },
  {
    term: 'MCU',
    def: 'A microcontroller — the chip on a control board. A printer often has several: the mainboard, a toolhead board, the Linux host’s “process MCU”, etc. Each runs its own Klipper firmware.',
  },
  {
    term: 'Host ↔ MCU sync',
    def: 'The firmware on an MCU must match the host’s Klipper version. If it drifts (e.g. after a host update), you get a “version mismatch” — reflash that MCU to fix it.',
  },
  {
    term: 'Katapult / DFU',
    def: 'Bootloaders that let you flash an MCU over USB or CAN without pulling an SD card. Katapult is the modern Klipper bootloader; DFU is STM32’s built-in one.',
  },
  {
    term: 'Flashing',
    def: 'Writing new firmware onto an MCU. The board usually needs to be in its bootloader first (Katapult / DFU / a reset).',
  },
  {
    term: 'Profile',
    def: 'A saved firmware configuration (Kconfig / menuconfig) for a board, so you can rebuild the exact same firmware later.',
  },
]

export const HELP: Record<HelpTopic, HelpEntry> = {
  glossary: {
    title: 'Firmware terms',
    body: 'A quick glossary for this widget:',
    illo: 'mcu',
  },
  overview: {
    title: 'What this widget does',
    body: 'Build and flash the Klipper firmware on every control board (MCU) of your printer — from one place, no command line. It shows each MCU’s version and whether it matches the host, lets you configure and build firmware per board, and flashes over Katapult / DFU / SD card.',
    illo: 'flash',
  },
  guided: {
    title: 'Guided new-board flow',
    body: 'A four-step checklist to get a new control board running matching firmware: detect the board, configure & build a profile, add & assign the device, then build & flash and verify it’s in sync with the host. Each step opens the right tab and turns green once the live state satisfies it, so you always know what’s next. Nothing here flashes on its own — it guides you to the existing tools, which keep their own confirms.',
    illo: 'flash',
  },
  status: {
    title: 'Host & MCU versions',
    body: 'The host runs Klipper; every MCU must run firmware built from the same version. A ⚠ on a device means its firmware is out of sync with the host — rebuild and reflash it. The Linux host’s own “process MCU” is shown too (Moonraker can’t report its version, so FilaMind tracks it).',
    illo: 'sync',
  },
  toolchain: {
    title: 'Toolchain badges',
    body: 'These show which build/flash tools are present on the host: Klipper (the source + build system), Katapult, flashtool, dfu-util, avrdude, can-utils. A ✗ means that tool isn’t installed — you only need the ones your boards use. The “setup” badge flags host issues (sudoers, udev rules) with fix-it hints.',
    illo: 'tool',
  },
  services: {
    title: 'Services',
    body: 'Start / stop / restart the host services (Klipper, Moonraker, …). Flashing usually stops Klipper so it releases the serial port, then restarts it afterwards — these controls let you do it by hand if needed.',
    illo: 'tool',
  },
  devices: {
    title: 'Devices',
    body: 'Each registered board, with its build/flash actions. “Build” compiles firmware for the board’s profile; “Flash” writes it; “build & flash” does both. The batch buttons (Build all / Flash all / Flash ready) operate on every device at once. Add or attach boards in the Devices manager.',
    illo: 'flash',
  },
  configure: {
    title: 'Configure & build firmware',
    body: 'Pick a board profile and edit its Klipper build options (the Kconfig menu) — toggle “option docs” to read what each setting does, right there. Then “build profile” compiles the firmware and saves the profile so the exact same build can be reproduced later. This builds the shared profile; you flash it to a specific board from the Status tab.',
    illo: 'tool',
  },
  external: {
    title: 'External firmware',
    body: 'Flash a pre-built firmware binary you didn’t compile here — a vendor’s `.bin` (e.g. a Beacon, an ERCF board, a CAN toolhead). Register the file, set its flash method and offset, then flash it like any board (behind the same confirm gate). FilaMind inspects the binary best-effort (detected version / MCU / build config) and can diff two files so you can see what changed.',
    illo: 'flash',
  },
  flash: {
    title: 'Build → flash safely',
    body: 'Flashing touches hardware, so FilaMind guards it: it won’t flash mid-print, it stops/restarts Klipper around the operation, and it confirms before irreversible steps. After a flash the board re-enumerates and its reported version updates so you can confirm success.',
    illo: 'flash',
  },
}

/** The practical build→flash quick guide, shown once at the top. */
export const STEPS: string[] = [
  'Check each MCU’s version against the host — a ⚠ badge flags firmware that’s out of sync.',
  'Configure a board’s firmware (Configure →) and save it as a profile, so it rebuilds identically.',
  'Build the firmware for that profile and watch the live log for errors.',
  'Put the board in its bootloader (Katapult / DFU) if needed, then Flash — Klipper is stopped and restarted around it.',
  'After flashing, the board re-enumerates and its version updates here — confirm it now matches the host.',
]
