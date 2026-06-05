// Pure helpers for i18n tooling — used by the CI key-diff (`i18n-keydiff.mjs`), the
// pseudo-localization dev aid (`i18n-pseudo.mjs`), and the vitest suite. Plain ESM (no TypeScript)
// so the CLI scripts run under bare `node` with zero build step.

/** Recursively collect dotted leaf-key paths (e.g. `shell.language.select`) from a message tree. */
export function flattenKeys(obj, prefix = '') {
  const keys = []
  for (const [k, v] of Object.entries(obj ?? {})) {
    const path = prefix ? `${prefix}.${k}` : k
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      keys.push(...flattenKeys(v, path))
    } else {
      keys.push(path)
    }
  }
  return keys
}

/**
 * Structural diff of a locale's keys against the reference (`en`). Returns the keys the locale is
 * missing and the extra keys it carries — both must be empty for the catalogs to be in lock-step.
 */
export function diffKeys(referenceKeys, localeKeys) {
  const ref = new Set(referenceKeys)
  const loc = new Set(localeKeys)
  return {
    missing: [...ref].filter((k) => !loc.has(k)).sort(),
    extra: [...loc].filter((k) => !ref.has(k)).sort(),
  }
}

// Latin look-alikes used to accent text so any un-externalized (hardcoded) English stands out.
const ACCENTS = {
  a: 'á', b: 'ƀ', c: 'ç', d: 'ð', e: 'é', f: 'ƒ', g: 'ǧ', h: 'ħ', i: 'í', j: 'ĵ', k: 'ķ',
  l: 'ł', m: 'ɱ', n: 'ñ', o: 'ó', p: 'þ', q: 'ʠ', r: 'ŕ', s: 'š', t: 'ť', u: 'ú', v: 'ʋ',
  w: 'ŵ', x: 'x', y: 'ý', z: 'ž',
  A: 'Á', B: 'Ɓ', C: 'Ç', D: 'Ð', E: 'É', F: 'Ƒ', G: 'Ǧ', H: 'Ħ', I: 'Í', J: 'Ĵ', K: 'Ķ',
  L: 'Ł', M: 'Ɱ', N: 'Ñ', O: 'Ó', P: 'Þ', Q: 'Ǫ', R: 'Ŕ', S: 'Š', T: 'Ť', U: 'Ú', V: 'Ʋ',
  W: 'Ŵ', X: 'X', Y: 'Ý', Z: 'Ž',
}

/**
 * Pseudo-localize one string: accent its letters, pad it ~40% wider, and bracket it. Text inside
 * `{...}` (named args and ICU `plural`/`select` syntax) is copied verbatim so messages stay valid.
 * Brackets make missing/clipped translations obvious; the padding surfaces RTL/expansion overflow
 * in the fixed-width Neo-Brutalist chrome before any real translator is involved.
 */
export function pseudoize(s) {
  if (typeof s !== 'string') return s
  let out = ''
  let depth = 0
  for (const ch of s) {
    if (ch === '{') {
      depth += 1
      out += ch
    } else if (ch === '}') {
      if (depth > 0) depth -= 1
      out += ch
    } else {
      out += depth > 0 ? ch : (ACCENTS[ch] ?? ch)
    }
  }
  const padLen = Math.ceil([...out].length * 0.4)
  const pad = padLen > 0 ? ' ' + '·'.repeat(padLen) : ''
  return `⟦${out}${pad}⟧`
}

/** Deep-map `pseudoize` over a whole message tree (strings transformed, structure preserved). */
export function pseudoizeTree(obj) {
  if (typeof obj === 'string') return pseudoize(obj)
  if (Array.isArray(obj)) return obj.map(pseudoizeTree)
  if (obj && typeof obj === 'object') {
    const out = {}
    for (const [k, v] of Object.entries(obj)) out[k] = pseudoizeTree(v)
    return out
  }
  return obj
}
