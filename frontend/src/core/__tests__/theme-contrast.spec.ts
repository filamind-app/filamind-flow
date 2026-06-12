/** Contrast regression guard for the theme palettes.
 *
 *  Parses every `[data-theme]` block (and the `:root` light defaults) out of main.css and
 *  asserts the token contract's hard WCAG constraints — the ones the palettes are calibrated
 *  against. If a future color tweak breaks badge readability or chart visibility, this fails
 *  with the exact theme/token/ratio.
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

import { THEME_META } from '../theme'

const css = readFileSync(resolve(__dirname, '../../assets/styles/main.css'), 'utf-8')

type Palette = Record<string, [number, number, number]>

function parseBlock(selector: string): Palette {
  const start = css.indexOf(selector)
  expect(start, `missing ${selector}`).toBeGreaterThanOrEqual(0)
  const body = css.slice(css.indexOf('{', start) + 1, css.indexOf('}', start))
  const out: Palette = {}
  for (const m of body.matchAll(/--c-([a-z-]+):\s*(\d+)\s+(\d+)\s+(\d+)/g)) {
    out[m[1]] = [Number(m[2]), Number(m[3]), Number(m[4])]
  }
  return out
}

function luminance([r, g, b]: [number, number, number]): number {
  const lin = (c: number) => {
    const s = c / 255
    return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
  }
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
}

function ratio(a: [number, number, number], b: [number, number, number]): number {
  const la = luminance(a)
  const lb = luminance(b)
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05)
}

const themes: Record<string, Palette> = { light: parseBlock(':root') }
for (const meta of THEME_META) {
  if (meta.key !== 'light') themes[meta.key] = parseBlock(`[data-theme='${meta.key}']`)
}

describe.each(Object.entries(themes))('theme %s', (_name, p) => {
  it('keeps text readable on page and cards', () => {
    expect(ratio(p.ink, p.paper)).toBeGreaterThanOrEqual(9)
    expect(ratio(p.ink, p.surface)).toBeGreaterThanOrEqual(8)
  })

  it('keeps ink-texted badges readable (lime / yellow / cyan)', () => {
    for (const accent of ['brand-lime', 'brand-yellow', 'brand-cyan'] as const) {
      expect(ratio(p[accent], p.ink), accent).toBeGreaterThanOrEqual(4)
    }
  })

  it('keeps the danger button readable (surface text on red)', () => {
    expect(ratio(p['brand-red'], p.surface)).toBeGreaterThanOrEqual(3)
  })

  it('keeps chart strokes visible on the page background', () => {
    for (const accent of [
      'brand-lime',
      'brand-yellow',
      'brand-cyan',
      'brand-blue',
      'brand-pink',
      'brand-red',
    ] as const) {
      expect(ratio(p[accent], p.paper), accent).toBeGreaterThanOrEqual(2)
    }
  })
})

it('theme.ts preview swatches stay in sync with main.css (paper/surface/ink)', () => {
  for (const meta of THEME_META) {
    const p = themes[meta.key]
    const hex = (rgb: [number, number, number]) =>
      '#' + rgb.map((c) => c.toString(16).padStart(2, '0')).join('')
    expect(meta.swatch.paper, meta.key).toBe(hex(p.paper))
    expect(meta.swatch.surface, meta.key).toBe(hex(p.surface))
    expect(meta.swatch.ink, meta.key).toBe(hex(p.ink))
  }
})
