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
      paper: '#160f2e',
      surface: '#251a4e',
      ink: '#f4efff',
      accents: ['#6e7cff', '#ff4fd8', '#ff3355'],
    },
  },
  {
    key: 'midnight',
    labelKey: 'theme.midnight',
    descKey: 'theme.desc.midnight',
    swatch: {
      paper: '#0a1322',
      surface: '#13223c',
      ink: '#e8f1fd',
      accents: ['#4c8dff', '#087890', '#d05fa2'],
    },
  },
  {
    key: 'dark',
    labelKey: 'theme.dark',
    descKey: 'theme.desc.dark',
    swatch: {
      paper: '#15191f',
      surface: '#21272f',
      ink: '#edf1f7',
      accents: ['#5b9bf5', '#c2608e', '#a16207'],
    },
  },
  {
    key: 'ocean',
    labelKey: 'theme.ocean',
    descKey: 'theme.desc.ocean',
    swatch: {
      paper: '#062420',
      surface: '#0b332d',
      ink: '#e7faf3',
      accents: ['#008080', '#fb6f84', '#f25a3c'],
    },
  },
  {
    key: 'sunset',
    labelKey: 'theme.sunset',
    descKey: 'theme.desc.sunset',
    swatch: {
      paper: '#2a1226',
      surface: '#3d1d36',
      ink: '#fdf1e3',
      accents: ['#f0452e', '#ff7aa8', '#8a7cf0'],
    },
  },
  {
    key: 'light',
    labelKey: 'theme.light',
    descKey: 'theme.desc.light',
    swatch: {
      paper: '#f3e8cd',
      surface: '#fffcf0',
      ink: '#1a1408',
      accents: ['#ffd60a', '#d61f6f', '#2b4fd8'],
    },
  },
  {
    key: 'contrast',
    labelKey: 'theme.contrast',
    descKey: 'theme.desc.contrast',
    swatch: {
      paper: '#000000',
      surface: '#181818',
      ink: '#ffffff',
      accents: ['#3d7bff', '#ff3da6', '#ff2424'],
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
