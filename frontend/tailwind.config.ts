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
        ink: '#111111',
        paper: '#f5f1e8',
        surface: '#fffdf5',
        brand: {
          yellow: '#ffd400',
          pink: '#ff5c8a',
          cyan: '#00e0c6',
          lime: '#9ae600',
          blue: '#5b8cff',
          red: '#ff5247',
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
        brutal: '4px',
      },
      boxShadow: {
        'brutal-sm': '2px 2px 0 0 #111111',
        brutal: '4px 4px 0 0 #111111',
        'brutal-lg': '7px 7px 0 0 #111111',
      },
    },
  },
  plugins: [],
} satisfies Config
