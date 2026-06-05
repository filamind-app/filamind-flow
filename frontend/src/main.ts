import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import './assets/styles/main.css'
import { i18n, initLocale } from './core/i18n'
import { registerWidgets } from './widgets'

const app = createApp(App)
app.use(createPinia())
app.use(i18n)

// Feature widgets self-register here. The scaffold ships with none.
registerWidgets()

// Resolve the user's locale (stored → browser → en) and set <html lang/dir> before first paint,
// so an RTL user never flashes LTR English. en needs no fetch (it's bundled), so this is instant
// for the common case and only awaits a chunk for a stored non-English locale.
void initLocale().finally(() => app.mount('#app'))
