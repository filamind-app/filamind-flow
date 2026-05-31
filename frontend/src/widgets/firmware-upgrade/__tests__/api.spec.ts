import { describe, expect, it } from 'vitest'

import { filenameFromDisposition } from '../api'

describe('filenameFromDisposition', () => {
  it('reads a plain quoted filename', () => {
    expect(filenameFromDisposition('attachment; filename="host-mcu.elf"', 'x.bin')).toBe(
      'host-mcu.elf',
    )
  })

  it('reads an unquoted filename', () => {
    expect(filenameFromDisposition('attachment; filename=board.bin', 'x.bin')).toBe('board.bin')
  })

  it('decodes the RFC 5987 form for names with spaces', () => {
    // Starlette emits this when the profile name contains a space.
    expect(filenameFromDisposition("attachment; filename*=utf-8''Linux%20host.elf", 'x.bin')).toBe(
      'Linux host.elf',
    )
  })

  it('falls back when no filename is present', () => {
    expect(filenameFromDisposition('attachment', 'Linux host.bin')).toBe('Linux host.bin')
    expect(filenameFromDisposition('', 'Linux host.bin')).toBe('Linux host.bin')
  })
})
