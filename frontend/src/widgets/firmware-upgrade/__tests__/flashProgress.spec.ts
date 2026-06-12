import { describe, expect, it } from 'vitest'

import { parseFlashStatus, stripPhaseMarkers } from '../flashProgress'

// A representative successful serial+Katapult flash, as the backend streams it.
const OK_LOG = [
  '::phase::start',
  '>>> Flashing klipper.bin → /dev/ttyACM0 via serial',
  '::phase::stop',
  '>>> Stopping Klipper to free the device…',
  '::phase::boot',
  '>>> Requesting /dev/ttyACM0 to enter its bootloader…',
  '::phase::write',
  '>>> python3 flashtool.py -d /dev/ttyACM0',
  'Writing 0x1000 bytes...',
  'Done',
  '::phase::restart',
  '>>> Restarting Klipper…',
  '::phase::done',
  '>>> Flash sequence complete — verify the board reconnects in Mainsail.',
].join('\n')

describe('stripPhaseMarkers', () => {
  it('removes only the ::phase:: lines, keeping the human log', () => {
    const out = stripPhaseMarkers(OK_LOG)
    expect(out).not.toMatch(/::phase::/)
    expect(out).toContain('>>> Flashing klipper.bin')
    expect(out).toContain('Writing 0x1000 bytes...')
  })
})

describe('parseFlashStatus', () => {
  it('reaches done at 100% with no errors on a clean flash', () => {
    const s = parseFlashStatus(OK_LOG, false)
    expect(s.phase).toBe('done')
    expect(s.done).toBe(true)
    expect(s.failed).toBe(false)
    expect(s.errors).toEqual([])
    expect(s.fraction).toBe(1)
  })

  it('tracks the furthest phase mid-flash and never shows full while running', () => {
    const partial = OK_LOG.split('\n').slice(0, 8).join('\n') // up to write
    const s = parseFlashStatus(partial, true)
    expect(s.phase).toBe('write')
    expect(s.done).toBe(false)
    expect(s.fraction).toBeGreaterThan(0)
    expect(s.fraction).toBeLessThanOrEqual(0.95)
  })

  it('collects real failures from !! lines and marks the run failed', () => {
    const failed = [
      '::phase::start',
      '>>> Flashing klipper.bin → can0 via can',
      '::phase::write',
      '!! cannot run flashtool.py: No such file or directory',
      'some benign trailing chatter',
    ].join('\n')
    const s = parseFlashStatus(failed, false)
    expect(s.failed).toBe(true)
    expect(s.errors).toEqual(['cannot run flashtool.py: No such file or directory'])
    expect(s.done).toBe(false)
    expect(s.fraction).toBeLessThan(1)
  })

  it('does not flag benign command-window noise as an error', () => {
    const noisy = [
      '::phase::stop',
      '>>> Stopping Klipper to free the device…',
      'Device is not marked Katapult — skipping reboot-to-bootloader.',
      '::phase::write',
      'make: Nothing to be done.',
      '::phase::done',
      '>>> Flash sequence complete.',
    ].join('\n')
    const s = parseFlashStatus(noisy, false)
    expect(s.errors).toEqual([])
    expect(s.done).toBe(true)
  })

  it('starts near zero before any phase marker', () => {
    const s = parseFlashStatus('warming up\n', true)
    expect(s.phase).toBeNull()
    expect(s.fraction).toBeGreaterThan(0)
    expect(s.fraction).toBeLessThan(0.1)
  })
})
