import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

vi.mock('@/core/moonraker', () => ({
  resolveEndpoints: () => ({
    httpUrl: 'http://test',
    wsUrl: 'ws://test',
    backendUrl: 'http://test',
  }),
}))

import { i18n } from '@/core/i18n'

import CameraView from '../CameraView.vue'

function mountCam(props: Record<string, unknown> = {}) {
  return mount(CameraView, {
    props: { active: false, ...props }, // active:false → no polling timer during the test
    global: { plugins: [i18n] },
  })
}

describe('CameraView', () => {
  it('renders inline (not fixed, no controls) by default', () => {
    const w = mountCam()
    expect(w.classes()).not.toContain('fixed')
    expect(w.findAll('button')).toHaveLength(0)
    w.unmount()
  })

  it('renders as a fixed PiP with size + collapse controls when pip', () => {
    const w = mountCam({ pip: true })
    expect(w.classes()).toContain('fixed')
    expect(w.findAll('button')).toHaveLength(2) // enlarge/shrink + minimize/maximize
    w.unmount()
  })

  it('hides the feed when minimized and restores it', async () => {
    const w = mountCam({ pip: true })
    // the feed container is driven by `collapsed` via v-show (sets inline display:none)
    const feedDisplay = () =>
      (w.find('[data-testid="cam-feed"]').element as HTMLElement).style.display
    // the collapse control toggles its aria-label between Minimize/Maximize
    const collapseBtn = () =>
      w.findAll('button').find((b) => /imize/i.test(b.attributes('aria-label') ?? ''))!
    expect(feedDisplay()).not.toBe('none')
    await collapseBtn().trigger('click') // minimize
    expect(feedDisplay()).toBe('none')
    await collapseBtn().trigger('click') // restore
    expect(feedDisplay()).not.toBe('none')
    w.unmount()
  })
})
