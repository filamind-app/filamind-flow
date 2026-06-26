import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { FULL_CONTROL, mergeSubscriptions } from '@filamind-app/core'

import TouchApp from './TouchApp.vue'
import './assets/touch.css'
import { i18n, detectLocale, setLocale, applyDocumentLocale } from '@/core/i18n'
import { initTheme } from './core/theme'
import { settingsStore } from './core/settings'
import { session } from './core/session'

// The native flow touch entry (served at :8090/touch, loaded by the Tauri kiosk). A standalone
// touch-first app sharing the suite themes via @filamind-app/core and the flow's i18n catalogs.
async function bootstrap(): Promise<void> {
  await settingsStore.hydrate()
  initTheme()

  // The control baseline plus the heaters + state the header shows.
  session.setSubscriptions(
    mergeSubscriptions(FULL_CONTROL, {
      extruder: ['temperature', 'target'],
      heater_bed: ['temperature', 'target'],
      print_stats: ['state'],
    }),
  )

  const locale = detectLocale()
  await setLocale(locale)
  applyDocumentLocale(locale)

  const app = createApp(TouchApp)
  app.use(createPinia())
  app.use(i18n)
  app.mount('#app')

  // Drop the boot splash once the app has mounted.
  const splash = document.getElementById('fm-splash')
  if (splash) {
    splash.style.opacity = '0'
    setTimeout(() => splash.remove(), 300)
  }
}

void bootstrap()
