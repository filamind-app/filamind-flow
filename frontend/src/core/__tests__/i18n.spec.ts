import { beforeEach, describe, expect, it } from 'vitest'

import { diffKeys, flattenKeys, pseudoize, pseudoizeTree } from '../../../scripts/i18n-lib.mjs'
import { availableLocales, detectLocale, i18n, LOCALE_META, matchLocale, setLocale } from '../i18n'

describe('i18n key tooling', () => {
  it('flattens a nested message tree to dotted paths', () => {
    expect(flattenKeys({ a: { b: 'x' }, c: 'y' }).sort()).toEqual(['a.b', 'c'])
  })

  it('diffs a locale key set against the reference', () => {
    const d = diffKeys(['a', 'b', 'c'], ['a', 'c', 'z'])
    expect(d.missing).toEqual(['b'])
    expect(d.extra).toEqual(['z'])
  })
})

describe('pseudo-localization', () => {
  it('accents letters and pads/brackets while preserving {args}', () => {
    const out = pseudoize('Flash {n} devices')
    expect(out.startsWith('⟦')).toBe(true)
    expect(out.endsWith('⟧')).toBe(true)
    expect(out).toContain('{n}') // named args copied verbatim
    expect(out).not.toContain('Flash') // letters were accented
    expect(out.length).toBeGreaterThan('Flash {n} devices'.length) // ~40% wider
  })

  it('deep-maps over a tree, transforming only strings', () => {
    const t = pseudoizeTree({ a: 'Hi', b: { c: 'Yo' } })
    expect(t.a).toMatch(/^⟦/)
    expect(t.b.c).toMatch(/^⟦/)
  })
})

describe('i18n instance', () => {
  it('bundles en eagerly and resolves namespaced keys', () => {
    expect(i18n.global.t('common.appName')).toBe('FilaMind Flow')
    expect(i18n.global.t('shell.language.select')).toBe('Select language')
  })
})

describe('locale detection & switching', () => {
  beforeEach(() => {
    try {
      localStorage.clear()
    } catch {
      // ignore — jsdom always provides localStorage, this is belt-and-braces
    }
  })

  it('offers only locales that have a catalog (en in Phase 0)', () => {
    expect(availableLocales.map((m) => m.code)).toEqual(['en'])
  })

  it('matchLocale resolves base languages and rejects not-yet-available ones', () => {
    expect(matchLocale('en-US')).toBe('en')
    expect(matchLocale('ar-EG')).toBeNull() // ar declared but no catalog yet
    expect(matchLocale('fr')).toBeNull()
  })

  it('detectLocale falls back to en', () => {
    expect(detectLocale()).toBe('en')
  })

  it('setLocale reflects lang/dir on <html> and falls back for unavailable locales', async () => {
    await setLocale('en')
    expect(document.documentElement.lang).toBe('en')
    expect(document.documentElement.dir).toBe('ltr')

    // ar has no catalog yet → falls back to en rather than throwing.
    await setLocale('ar')
    expect(document.documentElement.lang).toBe('en')
  })

  it('pins Western digits and RTL for Arabic in the metadata', () => {
    expect(LOCALE_META.ar.numberingSystem).toBe('latn')
    expect(LOCALE_META.ar.dir).toBe('rtl')
  })
})
