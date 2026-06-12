// Client-side rendering of structured backend verdicts.
//
// Live-tool results carry translatable `{code, params}` parts next to the plain-English
// `verdict`/`messages` strings. When every code has a locale key we join the translated
// fragments; otherwise (older payloads, unknown codes) the English fallback is shown as-is.
import type { VerdictPart } from './types'

type TFn = (key: string, params?: Record<string, string | number>) => string
type TeFn = (key: string) => boolean

/** Translate `{code, params}` parts under `base.*`, falling back to `fallback` wholesale. */
export function verdictText(
  t: TFn,
  te: TeFn,
  base: string,
  parts: VerdictPart[] | undefined,
  fallback: string,
): string {
  if (!parts || !parts.length) return fallback
  const keys = parts.map((p) => `${base}.${p.code}`)
  if (!keys.every((k) => te(k))) return fallback
  return parts.map((p, i) => t(keys[i], p.params)).join(' · ')
}

/** Translate a single-code verdict under `base.*`, falling back to `fallback`. */
export function codeText(
  t: TFn,
  te: TeFn,
  base: string,
  code: string | undefined,
  params: Record<string, string | number> | undefined,
  fallback: string,
): string {
  if (!code) return fallback
  const key = `${base}.${code}`
  return te(key) ? t(key, params ?? {}) : fallback
}
