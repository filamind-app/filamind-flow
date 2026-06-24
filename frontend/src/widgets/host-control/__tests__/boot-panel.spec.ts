import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import { i18n } from '@/core/i18n'

vi.mock('../api', () => ({
  fetchBootInfo: () =>
    Promise.resolve({
      default_target: 'graphical.target',
      graphical: true,
      splash: { path: '/boot/splash.png', size: 2048 },
      plymouth_theme: 'spinner',
    }),
  bootSplashUrl: () => 'http://x/api/host/boot/splash?t=1',
}))

import BootPanel from '../BootPanel.vue'

describe('Host Control: Boot panel', () => {
  it('shows the default target, plymouth theme and the splash preview', async () => {
    const w = mount(BootPanel, { global: { plugins: [i18n] } })
    await flushPromises()
    const text = w.text()
    expect(text).toContain('graphical.target')
    expect(text).toContain('spinner')
    const img = w.find('img')
    expect(img.exists()).toBe(true)
    expect(img.attributes('src')).toContain('/api/host/boot/splash')
  })
})
