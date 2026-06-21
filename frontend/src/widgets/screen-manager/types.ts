/** Shapes for the KlipperScreen Studio widget (backed by `/api/screen/*`). */

export interface ScreenStatus {
  /** KlipperScreen is installed (in Moonraker's allowed services, or its conf exists). */
  present: boolean
  /** Moonraker can restart the service (it's in the allowed list). */
  restartable: boolean
  conf_exists: boolean
  theme: string | null
  language: string | null
}

/** The editor view of KlipperScreen.conf (from the shared config read). */
export interface ScreenConf {
  filename: string
  raw: string
  sha256: string
  [key: string]: unknown
}
