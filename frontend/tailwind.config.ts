import type { Config } from 'tailwindcss'

/**
 * Neo-Brutalism design tokens.
 *
 * The visual language: thick ink borders, hard (blur-free) offset shadows,
 * high-saturation flat accents on warm paper, chunky display type + monospace
 * for data. Components compose these tokens (see src/assets/styles/main.css).
 */
export default {
  content: ['./index.html', './src/**/*.{vue,ts}'],
  theme: {
    extend: {
      colors: {
        // Theme-driven via CSS custom properties (space-separated RGB triplets so
        // Tailwind's <alpha-value> slot still works, e.g. bg-ink/50). The triplets
        // are defined in src/assets/styles/main.css per [data-theme].
        ink: 'rgb(var(--c-ink) / <alpha-value>)',
        paper: 'rgb(var(--c-paper) / <alpha-value>)',
        surface: 'rgb(var(--c-surface) / <alpha-value>)',
        sidebar: 'rgb(var(--c-sidebar) / <alpha-value>)',
        // Text drawn on a solid accent fill (see --c-on-accent in main.css).
        'on-accent': 'rgb(var(--c-on-accent) / <alpha-value>)',
        brand: {
          yellow: 'rgb(var(--c-brand-yellow) / <alpha-value>)',
          pink: 'rgb(var(--c-brand-pink) / <alpha-value>)',
          cyan: 'rgb(var(--c-brand-cyan) / <alpha-value>)',
          lime: 'rgb(var(--c-brand-lime) / <alpha-value>)',
          blue: 'rgb(var(--c-brand-blue) / <alpha-value>)',
          red: 'rgb(var(--c-brand-red) / <alpha-value>)',
        },
      },
      fontFamily: {
        display: ['"Space Grotesk"', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
        // Arabic face (Space Grotesk has no Arabic glyphs). Applied via :lang(ar) in main.css.
        arabic: ['"IBM Plex Sans Arabic"', '"Noto Sans Arabic"', 'system-ui', 'sans-serif'],
      },
      borderWidth: {
        3: '3px',
      },
      borderRadius: {
        brutal: 'var(--nb-radius)',
      },
      boxShadow: {
        'brutal-sm': 'var(--nb-shadow-sm)',
        brutal: 'var(--nb-shadow)',
        'brutal-lg': 'var(--nb-shadow-lg)',
      },
    },
  },
  plugins: [],
} satisfies Config
