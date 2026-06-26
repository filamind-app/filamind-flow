// Bridges the core SettingsStore to the DOM: applies the Pharaonic --fm-* tokens whenever settings
// change, and mirrors the theme onto data-fm-* attributes. Same mechanism FilaMind screen + 3d use,
// so the flow touch app shares the suite themes (Tutankhamun / Horus / Anubis).
//
// NOTE: lang + dir are owned by the flow i18n (applyDocumentLocale), not by the theme, so the touch
// entry reuses the flow's locale state without the SettingsStore locale fighting it.
import { applySettings, type UserSettings } from '@filamind-app/core'
import { settingsStore } from './settings'

function apply(s: UserSettings): void {
  applySettings(s)
  if (typeof document === 'undefined') return
  const root = document.documentElement
  root.dataset.fmTheme = s.theme
  root.dataset.fmDensity = s.density
  root.dataset.fmMotif = s.motifDensity
  root.dataset.fmReduced = String(s.reducedMotion)
}

/** Apply current settings now and re-apply on every change (Observable emits immediately). */
export function initTheme(): void {
  settingsStore.settings.subscribe(apply)
}
