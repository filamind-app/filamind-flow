import { describe, expect, it } from 'vitest'

import { collapseDiff, diffLines, diffStats } from './diff'

describe('diffLines', () => {
  it('marks added, removed, and unchanged lines (a = current, b = backup)', () => {
    const rows = diffLines('a\nb\nc\n', 'a\nX\nc\n')
    expect(rows.map((r) => r.kind + ':' + r.text)).toEqual([
      'eq:a',
      'del:b', // 'b' is in current but not the backup
      'add:X', // 'X' is in the backup but not current
      'eq:c',
      'eq:', // trailing newline → empty final line, unchanged
    ])
  })

  it('counts added/removed in the stats', () => {
    const stats = diffStats(diffLines('a\nb\n', 'a\nb\nc\nd\n'))
    expect(stats).toEqual({ added: 2, removed: 0 })
  })

  it('returns all-eq for identical input', () => {
    const rows = diffLines('x\ny\n', 'x\ny\n')
    expect(rows.every((r) => r.kind === 'eq')).toBe(true)
  })
})

describe('collapseDiff', () => {
  it('folds a long run of unchanged lines into a single hidden marker', () => {
    const same = Array.from({ length: 20 }, (_, i) => `line${i}`).join('\n')
    const rows = diffLines(same + '\nKEEP\n', same + '\nCHANGED\n')
    const collapsed = collapseDiff(rows, 2)
    const marker = collapsed.find((r) => r.hidden)
    expect(marker).toBeTruthy()
    expect(marker!.hidden).toBeGreaterThan(0)
    // The actual change is still present after collapsing.
    expect(collapsed.some((r) => r.kind === 'del' && r.text === 'KEEP')).toBe(true)
    expect(collapsed.some((r) => r.kind === 'add' && r.text === 'CHANGED')).toBe(true)
  })
})
