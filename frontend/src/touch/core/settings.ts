// The touch app's single SettingsStore, persisted under the suite-shared key so theme + locale
// roam across surfaces (screen / 3d / flow-touch). Shared model via @filamind-app/core.
import { SettingsStore, localStoragePersistence } from '@filamind-app/core'

export const SETTINGS_KEY = 'filamind.settings'

export const settingsStore = new SettingsStore(localStoragePersistence(SETTINGS_KEY))
