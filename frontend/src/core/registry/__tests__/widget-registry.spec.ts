import { beforeEach, describe, expect, it } from 'vitest'
import { h } from 'vue'

import type { WidgetDefinition } from '../types'
import { widgetRegistry } from '../widget-registry'

function makeWidget(
  id: string,
  subscriptions?: WidgetDefinition['subscriptions'],
): WidgetDefinition {
  return {
    id,
    title: id,
    component: { render: () => h('div') },
    subscriptions,
  }
}

describe('widgetRegistry', () => {
  beforeEach(() => widgetRegistry.clear())

  it('registers and retrieves widgets', () => {
    widgetRegistry.register(makeWidget('temperature'))
    expect(widgetRegistry.get('temperature')?.id).toBe('temperature')
    expect(widgetRegistry.all()).toHaveLength(1)
  })

  it('rejects duplicate ids', () => {
    widgetRegistry.register(makeWidget('temperature'))
    expect(() => widgetRegistry.register(makeWidget('temperature'))).toThrow(/already registered/)
  })

  it('merges widget subscriptions, preferring null (all fields)', () => {
    widgetRegistry.register(makeWidget('a', { extruder: ['temperature'] }))
    widgetRegistry.register(makeWidget('b', { extruder: ['target'], heater_bed: null }))

    const merged = widgetRegistry.aggregateSubscriptions()

    expect(new Set(merged.extruder as string[])).toEqual(new Set(['temperature', 'target']))
    expect(merged.heater_bed).toBeNull()
  })
})
