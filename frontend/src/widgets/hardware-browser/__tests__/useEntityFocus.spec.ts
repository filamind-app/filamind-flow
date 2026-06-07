import { describe, expect, it } from 'vitest'

import type { RelatedRef } from '../types'
import { targetFor, useEntityFocus } from '../useEntityFocus'

function ref(partial: Partial<RelatedRef>): RelatedRef {
  return { type: 'board', id: 'x', ...partial }
}

describe('targetFor — maps a related ref to its hosting tab', () => {
  it('maps each entity type to the correct tab', () => {
    expect(targetFor(ref({ type: 'board', id: 'skr' }))?.tab).toBe('boards')
    expect(targetFor(ref({ type: 'driver', id: 'tmc2209' }))?.tab).toBe('drivers')
    expect(targetFor(ref({ type: 'motor', id: 'm1' }))?.tab).toBe('motors')
    expect(targetFor(ref({ type: 'host', id: 'cb1' }))?.tab).toBe('hosts')
    expect(targetFor(ref({ type: 'manufacturer', id: 'btt' }))?.tab).toBe('manufacturers')
    expect(targetFor(ref({ type: 'mcu', id: 'rp2040' }))?.tab).toBe('mcus')
  })

  it('routes catalog entities to the category tab and carries the category', () => {
    const t = targetFor(ref({ type: 'catalog', id: 'sensor-x', category: 'Sensors & Probes' }))
    expect(t).toEqual({
      tab: 'category',
      id: 'sensor-x',
      name: undefined,
      category: 'Sensors & Probes',
    })
  })

  it('returns null for an unknown type or a missing id', () => {
    expect(targetFor(ref({ type: 'widget', id: 'x' }))).toBeNull()
    expect(targetFor(ref({ type: 'board', id: '' }))).toBeNull()
  })

  it('carries the name through for the destination panel to search by', () => {
    expect(targetFor(ref({ type: 'board', id: 'skr', name: 'BTT SKR' }))?.name).toBe('BTT SKR')
  })
})

describe('useEntityFocus — the shared focus channel', () => {
  it('focusEntity publishes a fresh object so repeat clicks still trigger watchers', () => {
    const { focus, focusEntity, clear } = useEntityFocus()
    focusEntity({ tab: 'boards', id: 'a' })
    const first = focus.value
    focusEntity({ tab: 'boards', id: 'a' })
    expect(focus.value).not.toBe(first) // new reference each time
    expect(focus.value).toMatchObject({ tab: 'boards', id: 'a' })
    clear()
    expect(focus.value).toBeNull()
  })
})
