// Self-hosted fonts, bundled by Vite so the panel renders fully offline and pings no third party
// (no Google Fonts). Weights mirror what the UI uses; Arabic faces are included for the RTL UI.
import '@fontsource/ibm-plex-sans-arabic/400.css'
import '@fontsource/ibm-plex-sans-arabic/500.css'
import '@fontsource/ibm-plex-sans-arabic/700.css'
import '@fontsource/jetbrains-mono/400.css'
import '@fontsource/jetbrains-mono/700.css'
import '@fontsource/noto-sans-arabic/400.css'
import '@fontsource/noto-sans-arabic/700.css'
import '@fontsource/space-grotesk/400.css'
import '@fontsource/space-grotesk/500.css'
import '@fontsource/space-grotesk/700.css'
import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import './assets/styles/main.css'
import { i18n, initLocale } from './core/i18n'
import { detectSuiteHost } from './core/host/suite'
import { initTheme } from './core/theme'
import { registerWidgets } from './widgets'

const app = createApp(App)
app.use(createPinia())
app.use(i18n)

// Resolve the user's theme (stored → neon) and reflect it on <html data-theme>. The no-flash inline
// script in index.html already applied it before first paint; this syncs the reactive ref.
initTheme()

// Feature widgets self-register here. The scaffold ships with none.
registerWidgets()

// Probe whether FilaMind 3D is installed so the suite-gated widgets unlock at runtime (no rebuild).
// Fire-and-forget: the gate is reactive and defaults to locked until this resolves.
void detectSuiteHost()

// Resolve the user's locale (stored → browser → en) and set <html lang/dir> before first paint,
// so an RTL user never flashes LTR English. en needs no fetch (it's bundled), so this is instant
// for the common case and only awaits a chunk for a stored non-English locale.
void initLocale().finally(() => app.mount('#app'))
