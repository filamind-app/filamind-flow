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

export type ThemeKey = 'light' | 'dark' | 'neon' | 'contrast' | 'midnight' | 'ocean' | 'sunset'

/** Static preview colors for the theme menu (hex — previews must not depend on the ACTIVE
 *  theme's CSS vars, they show what each theme WOULD look like). Keep in sync with main.css. */
export interface ThemeSwatch {
  paper: string
  surface: string
  ink: string
  accents: [string, string, string]
}

export interface ThemeMeta {
  /** Stable key; written to ``<html data-theme>`` and persisted. */
  key: ThemeKey
  /** i18n key for the human label shown in the switcher (``theme.<key>``). */
  labelKey: string
  /** i18n key for the one-line description shown in the theme menu (``theme.desc.<key>``). */
  descKey: string
  /** Mini preview colors for the menu card. */
  swatch: ThemeSwatch
}

/**
 * Every theme the app ships, in switcher order. ``neon`` is the default (the dark-neon mockup
 * look the project is designed around).
 */
export const THEME_META: ThemeMeta[] = [
  {
    key: 'neon',
    labelKey: 'theme.neon',
    descKey: 'theme.desc.neon',
    swatch: {
      paper: '#190f32',
      surface: '#281946',
      ink: '#f5f2ff',
      accents: ['#00f0dc', '#ff64c8', '#ffeb32'],
    },
  },
  {
    key: 'midnight',
    labelKey: 'theme.midnight',
    descKey: 'theme.desc.midnight',
    swatch: {
      paper: '#0f172a',
      surface: '#1e293b',
      ink: '#e2e8f0',
      accents: ['#60a5fa', '#22d3ee', '#facc15'],
    },
  },
  {
    key: 'dark',
    labelKey: 'theme.dark',
    descKey: 'theme.desc.dark',
    swatch: {
      paper: '#18181c',
      surface: '#27272e',
      ink: '#e8eaf0',
      accents: ['#2dd4bf', '#60a5fa', '#facc15'],
    },
  },
  {
    key: 'ocean',
    labelKey: 'theme.ocean',
    descKey: 'theme.desc.ocean',
    swatch: {
      paper: '#06262d',
      surface: '#0d3842',
      ink: '#e0f7f4',
      accents: ['#40e0d0', '#66b2ff', '#ffd166'],
    },
  },
  {
    key: 'sunset',
    labelKey: 'theme.sunset',
    descKey: 'theme.desc.sunset',
    swatch: {
      paper: '#2a1824',
      surface: '#402634',
      ink: '#fff1e6',
      accents: ['#ffc857', '#ff7aa2', '#5eead4'],
    },
  },
  {
    key: 'light',
    labelKey: 'theme.light',
    descKey: 'theme.desc.light',
    swatch: {
      paper: '#f5f1e8',
      surface: '#fffdf5',
      ink: '#111111',
      accents: ['#ffd400', '#00e0c6', '#ff5c8a'],
    },
  },
  {
    key: 'contrast',
    labelKey: 'theme.contrast',
    descKey: 'theme.desc.contrast',
    swatch: {
      paper: '#050505',
      surface: '#141414',
      ink: '#ffffff',
      accents: ['#ffff00', '#00fff0', '#ff32b4'],
    },
  },
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
