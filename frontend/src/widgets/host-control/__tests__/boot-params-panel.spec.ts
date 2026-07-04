import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { i18n } from '@/core/i18n'

const mocks = vi.hoisted(() => ({
  fetchBootParams: vi.fn(),
  previewBootChange: vi.fn(),
  applyBootChange: vi.fn(),
}))

vi.mock('../api', () => ({
  fetchBootParams: mocks.fetchBootParams,
  previewBootChange: mocks.previewBootChange,
  applyBootChange: mocks.applyBootChange,
  revertBootFile: vi.fn(),
  rebootForBoot: vi.fn(),
  HostActionError: class HostActionError extends Error {},
}))

import BootParamsPanel from '../BootParamsPanel.vue'

const ARMBIAN_STATE = {
  platform: 'armbian',
  editable: true,
  reboot_required: false,
  files: [
    {
      name: 'armbianEnv.txt',
      path: '/boot/armbianEnv.txt',
      exists: true,
      format: 'armbian',
      raw_lines: 7,
      backups: [],
      keys: [
        { key: 'bootlogo', value: 'true' },
        { key: 'verbosity', value: '1' },
      ],
      overlays: ['dsi'],
      extraargs: ['cma=256M'],
    },
  ],
}

const PREVIEW = {
  ok: true,
  file: 'armbianEnv.txt',
  editable: true,
  diff: [
    '--- armbianEnv.txt',
    '+++ armbianEnv.txt (new)',
    '-overlays=dsi',
    '+overlays=dsi mcp2515',
  ],
  before_hash: 'abc',
  after_hash: 'def',
  validation: { errors: [], warnings: [] },
}

function mountPanel() {
  return mount(BootParamsPanel, { global: { plugins: [i18n] } })
}

describe('Host Control: Boot parameters panel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.fetchBootParams.mockResolvedValue(ARMBIAN_STATE)
    mocks.previewBootChange.mockResolvedValue(PREVIEW)
    mocks.applyBootChange.mockResolvedValue({ ok: true, refused: false, output: 'done' })
  })

  it('renders the curated cards for the detected platform', async () => {
    const w = mountPanel()
    await flushPromises()
    const text = w.text()
    expect(text).toContain('armbianEnv.txt')
    expect(text).toContain('CAN via MCP2515')
    expect(text).toContain('Reserved CMA memory')
  })

  it('stages an edit without writing, then previews and applies (gated)', async () => {
    const w = mountPanel()
    await flushPromises()

    // toggle the first capability (CAN via MCP2515) - stages an op, no API call yet
    await w.find('input[type="checkbox"]').setValue(true)
    expect(mocks.previewBootChange).not.toHaveBeenCalled()
    expect(w.text()).toContain('changed') // the per-item CHANGED badge

    // Preview builds the diff from staged ops
    const previewBtn = w.findAll('button').find((b) => b.text().includes('Preview changes'))!
    await previewBtn.trigger('click')
    await flushPromises()
    expect(mocks.previewBootChange).toHaveBeenCalledWith('armbianEnv.txt', expect.any(Array))
    expect(w.text()).toContain('overlays=dsi mcp2515')

    // Apply passes the previewed before_hash for optimistic concurrency
    const applyBtn = w.findAll('button').find((b) => b.text().trim() === 'Apply')!
    await applyBtn.trigger('click')
    await flushPromises()
    expect(mocks.applyBootChange).toHaveBeenCalledWith('armbianEnv.txt', expect.any(Array), 'abc')
  })

  it('shows a read-only banner on an unknown platform', async () => {
    mocks.fetchBootParams.mockResolvedValue({
      platform: 'unknown',
      editable: false,
      reboot_required: false,
      files: [],
    })
    const w = mountPanel()
    await flushPromises()
    expect(w.text()).toContain('read-only')
    expect(w.find('input[type="checkbox"]').exists()).toBe(false)
  })
})
