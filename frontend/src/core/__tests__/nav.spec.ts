import { describe, it, expect, beforeEach } from 'vitest'
import { defineComponent, h, nextTick } from 'vue'
import { mount } from '@vue/test-utils'

import { useNav, useHashTab } from '../nav'

describe('nav', () => {
  beforeEach(() => {
    // Reset to the empty home + a clean URL between tests (the nav state is a module singleton).
    history.replaceState(null, '', '/')
    useNav().go('dashboard')
  })

  it('go(view) sets the hash + current view and closes the mobile drawer', () => {
    const nav = useNav()
    nav.sidebarOpen.value = true
    nav.go('firmware-upgrade')
    expect(nav.current.value).toBe('firmware-upgrade')
    expect(window.location.hash).toBe('#firmware-upgrade')
    expect(nav.sidebarOpen.value).toBe(false)
  })

  it('go("dashboard") clears the hash (no bare "#")', () => {
    const nav = useNav()
    nav.go('config-editor')
    expect(window.location.hash).toBe('#config-editor')
    nav.go('dashboard')
    expect(nav.current.value).toBe('dashboard')
    expect(window.location.hash).toBe('')
  })

  it('a deep link uses view/tab in the hash', () => {
    useNav().go('firmware-upgrade', 'status')
    expect(window.location.hash).toBe('#firmware-upgrade/status')
  })

  it('a hashchange (back/forward or manual edit) updates the current view', () => {
    const nav = useNav()
    window.location.hash = '#machine-doctor'
    window.dispatchEvent(new Event('hashchange'))
    expect(nav.current.value).toBe('machine-doctor')
  })

  it('useHashTab lands a deep-linked tab on its target widget (and only that widget)', async () => {
    useNav().go('firmware-upgrade', 'status')
    const applied: string[] = []
    const other: string[] = []
    const Probe = defineComponent({
      setup() {
        useHashTab('firmware-upgrade', (t) => applied.push(t))
        useHashTab('config-editor', (t) => other.push(t))
        return () => h('div')
      },
    })
    mount(Probe)
    await nextTick()
    expect(applied).toEqual(['status'])
    expect(other).toEqual([]) // not its deep link → untouched
  })
})
