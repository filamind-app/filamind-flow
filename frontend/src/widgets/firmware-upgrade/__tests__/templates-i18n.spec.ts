import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { describe, expect, it } from 'vitest'

import { i18n } from '@/core/i18n'

import ExternalFirmwarePanel from '../ExternalFirmwarePanel.vue'
import FirmwareConfigEditor from '../FirmwareConfigEditor.vue'
import FirmwareDevicesPanel from '../FirmwareDevicesPanel.vue'
import FirmwareUpgradeWidget from '../FirmwareUpgradeWidget.vue'

function plugins() {
  return { global: { plugins: [i18n, createPinia()] } }
}

const t = i18n.global.t as unknown as (key: string, named?: object, plural?: number) => string

function noLeak(text: string): void {
  const m = text.match(/firmware\.(widget|guided|flashConfirm|configEditor|devices|external)\./)
  expect(m, m ? `leaked key: ${m[0]}` : '').toBeNull()
}

async function mountExpand(component: unknown): Promise<void> {
  const w = mount(component as never, plugins())
  const btn = w.find('button')
  if (btn.exists()) await btn.trigger('click')
  noLeak(w.text())
}

describe('Firmware templates render through i18n (no leaked keys)', () => {
  it('FirmwareUpgradeWidget — chrome + steps via tm()', () => {
    noLeak(mount(FirmwareUpgradeWidget, plugins()).text())
  })
  it('FirmwareConfigEditor', () => mountExpand(FirmwareConfigEditor))
  it('FirmwareDevicesPanel', () => mountExpand(FirmwareDevicesPanel))
  it('ExternalFirmwarePanel', () => mountExpand(ExternalFirmwarePanel))
})

describe('Firmware pipe-plurals select the right form', () => {
  it('widget setup-issue count', () => {
    expect(t('firmware.widget.healthIssues', { n: 1 }, 1)).toBe('1 setup issue')
    expect(t('firmware.widget.healthIssues', { n: 3 }, 3)).toBe('3 setup issues')
  })
  it('config-editor edits badge', () => {
    expect(t('firmware.configEditor.editsBadge', { n: 1 }, 1)).toBe('1 edit')
    expect(t('firmware.configEditor.editsBadge', { n: 2 }, 2)).toBe('2 edits')
  })
  it('devices restored count', () => {
    expect(t('firmware.devices.restored', { n: 1, extra: '' }, 1)).toBe('Restored 1 profile.')
    expect(t('firmware.devices.restored', { n: 4, extra: '' }, 4)).toBe('Restored 4 profiles.')
  })
})
