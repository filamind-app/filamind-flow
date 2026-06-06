import { ref } from 'vue'

/**
 * App-wide theme runtime — mirrors the i18n module's shape (see core/i18n.ts).
 *
 * Mechanism: themes are pure CSS. Every design token (colors, shadows, radius) is a CSS custom
 * property defined per ``[data-theme]`` in src/assets/styles/main.css, and Tailwind reads those
 * vars (see tailwind.config.ts). So switching a theme is one DOM attribute write —
 * ``<html data-theme="…">`` — and every existing utility (bg-paper, border-ink, shadow-brutal,
 * rounded-brutal, …) recolors with NO component edits.
 *
 * Drop-in extensibility: a new theme becomes selectable the moment its key is added to
 * ``THEME_META`` here *and* a matching ``[data-theme="…"]`` block exists in main.css — no
 * component changes.
 */

export type ThemeKey = 'light' | 'dark' | 'neon' | 'contrast'

export interface ThemeMeta {
  /** Stable key; written to ``<html data-theme>`` and persisted. */
  key: ThemeKey
  /** i18n key for the human label shown in the switcher (``theme.<key>``). */
  labelKey: string
}

/**
 * Every theme the app ships, in switcher order. ``neon`` is the default (the dark-neon mockup
 * look the project is designed around).
 */
export const THEME_META: ThemeMeta[] = [
  { key: 'neon', labelKey: 'theme.neon' },
  { key: 'dark', labelKey: 'theme.dark' },
  { key: 'light', labelKey: 'theme.light' },
  { key: 'contrast', labelKey: 'theme.contrast' },
]

export const DEFAULT_THEME: ThemeKey = 'neon'
const STORAGE_KEY = 'filamind-theme'

/** Themes offered by the switcher, in ``THEME_META`` order. */
export const availableThemes: ThemeMeta[] = THEME_META

function isThemeKey(value: string | null): value is ThemeKey {
  return !!value && THEME_META.some((t) => t.key === value)
}

/** The active theme, reactive so the switcher reflects the current choice. */
export const currentTheme = ref<ThemeKey>(DEFAULT_THEME)

/** Stored choice → default (``neon``). Only ever returns a known theme key. */
export function detectTheme(): ThemeKey {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (isThemeKey(stored)) return stored
  } catch {
    // localStorage can throw in private mode / sandboxed iframes — fall through to the default.
  }
  return DEFAULT_THEME
}

/** Reflect the active theme on the document so the CSS vars (and Tailwind tokens) recolor. */
export function applyTheme(key: ThemeKey): void {
  if (typeof document !== 'undefined') {
    document.documentElement.dataset.theme = key
  }
}

/** Activate, persist, and reflect a theme on ``<html>``. */
export function setTheme(key: ThemeKey): void {
  const target = isThemeKey(key) ? key : DEFAULT_THEME
  currentTheme.value = target
  applyTheme(target)
  try {
    localStorage.setItem(STORAGE_KEY, target)
  } catch {
    // Persistence is best-effort; a non-writable store just means the choice won't survive reload.
  }
}

/** Startup: resolve the user's theme and apply it (called from ``main.ts``). The no-flash inline
 *  script in index.html already set the attribute before first paint; this syncs the reactive ref
 *  (and re-applies, harmlessly) so the switcher starts on the right value. */
export function initTheme(): void {
  setTheme(detectTheme())
}
