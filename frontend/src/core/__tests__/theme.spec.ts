import { beforeEach, describe, expect, it } from 'vitest'

import {
  availableThemes,
  currentTheme,
  DEFAULT_THEME,
  detectTheme,
  setTheme,
  THEME_META,
} from '../theme'

describe('theme registry', () => {
  it('ships 7 themes with complete menu metadata', () => {
    expect(THEME_META).toHaveLength(7)
    const keys = THEME_META.map((m) => m.key)
    expect(keys).toEqual(
      expect.arrayContaining(['neon', 'midnight', 'dark', 'ocean', 'sunset', 'light', 'contrast']),
    )
    for (const meta of THEME_META) {
      expect(meta.labelKey).toBe(`theme.${meta.key}`)
      expect(meta.descKey).toBe(`theme.desc.${meta.key}`)
      expect(meta.swatch.accents).toHaveLength(3)
      // Swatch colors are static hex (previews must not depend on the active theme's CSS vars).
      for (const color of [meta.swatch.paper, meta.swatch.surface, meta.swatch.ink]) {
        expect(color).toMatch(/^#[0-9a-f]{6}$/i)
      }
    }
    expect(availableThemes).toBe(THEME_META)
  })
})

describe('setTheme / detectTheme', () => {
  beforeEach(() => {
    localStorage.clear()
    setTheme(DEFAULT_THEME)
  })

  it('applies, persists, and reflects a known theme', () => {
    setTheme('midnight')
    expect(currentTheme.value).toBe('midnight')
    expect(document.documentElement.dataset.theme).toBe('midnight')
    expect(localStorage.getItem('filamind-theme')).toBe('midnight')
    expect(detectTheme()).toBe('midnight')
  })

  it('falls back to the default for an unknown stored value', () => {
    localStorage.setItem('filamind-theme', 'hotdog-stand')
    expect(detectTheme()).toBe(DEFAULT_THEME)
  })
})
