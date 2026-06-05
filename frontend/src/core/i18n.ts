import { createI18n } from 'vue-i18n'

import enCommon from '../locales/en/common.json'
import enFirmware from '../locales/en/firmware.json'
import enInputShaping from '../locales/en/input-shaping.json'
import enMotorDrivers from '../locales/en/motor-drivers.json'
import enShell from '../locales/en/shell.json'

/**
 * App-wide internationalization (i18n Phase 0 — scaffolding).
 *
 * Design goals:
 *  - **Offline-first:** ``en`` is bundled eagerly so first paint never waits on a network fetch
 *    (a Klipper host is usually offline). Every other locale is a lazy chunk.
 *  - **Drop-in extensibility:** a language becomes selectable the moment a catalog folder exists
 *    under ``src/locales/<code>/`` — no component edits (see ``availableLocales``).
 *  - **Namespaced catalogs** mirror the code-split: ``common`` / ``shell`` / ``firmware`` /
 *    ``input-shaping`` / ``motor-drivers``. Each JSON file carries a single top-level namespace
 *    key that is merged into the locale's message object.
 *
 * Catalogs are intentionally near-empty in Phase 0 — externalizing the existing English copy
 * lands in later phases. This module only stands up the plumbing (no user-visible change).
 */

export type Direction = 'ltr' | 'rtl'

export interface LocaleMeta {
  /** BCP-47 code; used as the vue-i18n locale key and the ``<html lang>`` value. */
  code: string
  /** Endonym shown in the language switcher (always written in its own language). */
  label: string
  dir: Direction
  /**
   * Forced Unicode numbering system, if any. Arabic pins Western digits (``latn``) because this
   * is an engineering tool — operators cross-reference G-code and datasheets in ``1.7 A`` form.
   */
  numberingSystem?: string
}

/**
 * Every locale the project plans to ship. Declaration order is the switcher order. A locale here
 * is only *offered* once its catalog exists on disk (see ``availableLocales``); listing it early
 * lets detection and tooling know about it before the translation lands.
 */
export const LOCALE_META: Record<string, LocaleMeta> = {
  en: { code: 'en', label: 'English', dir: 'ltr' },
  ar: { code: 'ar', label: 'العربية', dir: 'rtl', numberingSystem: 'latn' },
  de: { code: 'de', label: 'Deutsch', dir: 'ltr' },
  'zh-Hans': { code: 'zh-Hans', label: '简体中文', dir: 'ltr' },
  fr: { code: 'fr', label: 'Français', dir: 'ltr' },
  es: { code: 'es', label: 'Español', dir: 'ltr' },
  ru: { code: 'ru', label: 'Русский', dir: 'ltr' },
}

export const DEFAULT_LOCALE = 'en'
const STORAGE_KEY = 'filamind.locale'

// --- Catalog loading ------------------------------------------------------

type JsonModule = { default: Record<string, unknown> }

// en is bundled eagerly (no fetch on first paint). Static imports keep it fully typed — it is the
// schema source for type-safe keys (see types/i18n.d.ts). Every other locale is a dynamic chunk,
// discovered and loaded on demand via the glob below.
const en = { ...enCommon, ...enShell, ...enFirmware, ...enInputShaping, ...enMotorDrivers }

// en is excluded — it's bundled eagerly above, so the dynamic glob must not also claim it
// (that would split it into a never-used chunk and warn at build).
const lazyCatalogs = import.meta.glob<JsonModule>(['../locales/*/*.json', '!../locales/en/*.json'])

function mergeModules(modules: JsonModule[]): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const m of modules) Object.assign(out, m.default)
  return out
}

function codeFromPath(path: string): string | null {
  const m = /\/locales\/([^/]+)\/[^/]+\.json$/.exec(path)
  return m ? m[1] : null
}

/** Locales with a catalog on disk, in ``LOCALE_META`` order — the switcher offers exactly these. */
export const availableLocales: LocaleMeta[] = (() => {
  const codes = new Set<string>([DEFAULT_LOCALE])
  for (const path of Object.keys(lazyCatalogs)) {
    const code = codeFromPath(path)
    if (code) codes.add(code)
  }
  return Object.values(LOCALE_META).filter((m) => codes.has(m.code))
})()

function isAvailable(code: string): boolean {
  return availableLocales.some((m) => m.code === code)
}

// --- number / date formats ------------------------------------------------
// Established now so later phases route values through vue-i18n (locale separators / digit system)
// instead of ``.toFixed()`` string-gluing. ar carries numberingSystem 'latn' from LOCALE_META.

function numberFmt(numberingSystem?: string): Record<string, Intl.NumberFormatOptions> {
  return {
    decimal: { style: 'decimal', maximumFractionDigits: 2, numberingSystem },
    integer: { style: 'decimal', maximumFractionDigits: 0, numberingSystem },
  }
}

function dateFmt(numberingSystem?: string): Record<string, Intl.DateTimeFormatOptions> {
  return {
    short: { year: 'numeric', month: 'short', day: 'numeric', numberingSystem },
    long: {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      numberingSystem,
    },
  }
}

const numberFormats = Object.fromEntries(
  Object.values(LOCALE_META).map((m) => [m.code, numberFmt(m.numberingSystem)]),
)
const datetimeFormats = Object.fromEntries(
  Object.values(LOCALE_META).map((m) => [m.code, dateFmt(m.numberingSystem)]),
)

// --- instance -------------------------------------------------------------

export const i18n = createI18n({
  legacy: false,
  globalInjection: true,
  locale: DEFAULT_LOCALE,
  fallbackLocale: DEFAULT_LOCALE,
  missingWarn: import.meta.env.DEV,
  fallbackWarn: false,
  messages: { en },
  numberFormats,
  datetimeFormats,
})

// --- detection / switching ------------------------------------------------

/** Resolve a browser/preference tag (``ar-EG``, ``zh``, ``de``) to an available locale code. */
export function matchLocale(pref: string): string | null {
  if (isAvailable(pref)) return pref
  const base = pref.split('-')[0].toLowerCase()
  if (isAvailable(base)) return base
  if (base === 'zh' && isAvailable('zh-Hans')) return 'zh-Hans'
  const byBase = availableLocales.find((m) => m.code.split('-')[0].toLowerCase() === base)
  return byBase ? byBase.code : null
}

/** Stored choice → browser languages → ``en``. Only ever returns an available locale. */
export function detectLocale(): string {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored && isAvailable(stored)) return stored
  } catch {
    // localStorage can throw in private mode / sandboxed iframes — fall through to detection.
  }
  const prefs = (typeof navigator !== 'undefined' && navigator.languages) || []
  for (const p of prefs) {
    const matched = matchLocale(p)
    if (matched) return matched
  }
  return DEFAULT_LOCALE
}

const loaded = new Set<string>([DEFAULT_LOCALE])

/** Fetch and merge a locale's catalog chunks (idempotent; no-op for ``en`` and repeats). */
export async function loadLocaleMessages(code: string): Promise<void> {
  if (loaded.has(code)) return
  const loaders = Object.entries(lazyCatalogs)
    .filter(([path]) => codeFromPath(path) === code)
    .map(([, load]) => load())
  if (!loaders.length) return
  const modules = await Promise.all(loaders)
  i18n.global.mergeLocaleMessage(code, mergeModules(modules))
  loaded.add(code)
}

/** Reflect the active locale on the document so CSS (``[dir=rtl]``) and AT see it. */
export function applyDocumentLocale(code: string): void {
  const meta = LOCALE_META[code] ?? LOCALE_META[DEFAULT_LOCALE]
  if (typeof document !== 'undefined') {
    document.documentElement.lang = meta.code
    document.documentElement.dir = meta.dir
  }
}

/** Load (if needed), activate, persist, and reflect a locale on ``<html>``. */
export async function setLocale(code: string): Promise<void> {
  const target = isAvailable(code) ? code : DEFAULT_LOCALE
  await loadLocaleMessages(target)
  i18n.global.locale.value = target
  try {
    localStorage.setItem(STORAGE_KEY, target)
  } catch {
    // Persistence is best-effort; a non-writable store just means the choice won't survive reload.
  }
  applyDocumentLocale(target)
}

/** Startup: resolve the user's locale and apply it before first paint (called from ``main.ts``). */
export async function initLocale(): Promise<void> {
  await setLocale(detectLocale())
}
