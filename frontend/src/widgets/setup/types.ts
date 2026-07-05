export interface SetupComponent {
  id: string
  name: string
  kind: string
  repo: string
  type: string
  deps?: string[]
  first_party?: boolean
  /** systemd unit name when this component runs as a service (drives restart / logs / health). */
  service?: string
  /** One-line description of what the component does. */
  desc?: string
  /** For web UIs: the port the component is served on by default. */
  default_port?: number
  /** Subcommand for this app's DEFAULT install (FilaMind screen → `native`, the kiosk). */
  install_args?: string
  /** An ADDITIONAL managed deployment installable by its own button (FilaMind 3d → `agent`, the
   *  :8030 service that unlocks the suite widgets). Distinct from `install_args`: when they're
   *  equal the "service" is just the main install, so no extra button is shown (FilaMind screen). */
  service_install?: string
  /** Human note explaining what `service_install` adds (shown on the agent button's row). */
  service_install_hint?: string
  /** A third-party web UI's release-zip asset (`mainsail.zip`) - marks it one-click installable. */
  release_asset?: string
  /** The Moonraker `[update_manager]` block type written on install (`web` | `git_repo`). */
  mr_type?: string
  /** A `printer.cfg` `[include <file>]` this add-on needs to be wired in (toggle in the widget). */
  config_include?: string
  /** Klipper-extra module filenames this component symlinks into `klippy/extras`. */
  extras?: string[]
  /** An information-only card (nothing to install here - e.g. CAN tools ship inside Klipper). */
  guide?: boolean
  /** The component's installer prompts interactively (best-effort headless). */
  interactive?: boolean
}

export interface SetupGroup {
  group: string
  components: SetupComponent[]
}

export interface SetupCatalog {
  schema: number
  groups: SetupGroup[]
}

export interface SetupComponentStatus {
  /** 'installed' | 'not-installed' (best-effort). */
  status: string
  /** Installed version (managed components + git checkouts); '' when unknown. */
  version: string
  /** Latest available version: the remote version for installed components, or the latest published
   *  release/tag for not-installed ones; '' when unknown (e.g. GitHub quota short, no tags). */
  latest: string
  /** True only when an installed component is behind its remote (drives the Update button). */
  updateAvailable: boolean
  /** For an installed first-party nginx app (FilaMind 3d / screen): the port it's served on. */
  port?: number
  /** Whether the component is running right now: an nginx app's port responds, or its systemd unit
   *  is active. Present for any installed component with a runtime (undefined otherwise). */
  running?: boolean
  /** For an add-on with a `config_include`: whether that `[include]` is currently in printer.cfg. */
  includeActive?: boolean
  /** Whether Moonraker's update manager already tracks this component (hides the register action). */
  managed?: boolean
}

/** Periodic auto-update preferences (opt-in; applied only while the printer is idle). */
export interface SetupAutoUpdate {
  enabled: boolean
  intervalHours: number
}

export interface SetupStatus {
  /** component id → its install state, versions and update flag. */
  status: Record<string, SetupComponentStatus>
  /** Whether GUI install/update/remove is enabled on this host. */
  writesEnabled: boolean
  /** Auto-update preferences for this host. */
  autoUpdate: SetupAutoUpdate
}

export interface SetupActionResult {
  ok?: boolean
  output?: string
}
