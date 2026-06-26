export interface SetupComponent {
  id: string
  name: string
  kind: string
  repo: string
  type: string
  deps?: string[]
  first_party?: boolean
  /** One-line description of what the component does. */
  desc?: string
  /** For web UIs: the port the component is served on by default. */
  default_port?: number
  /** A `scripts/install.sh` subcommand that installs this app's managed systemd service (FilaMind 3d
   *  → `agent`, FilaMind screen → `native`). Surfaced as a copyable, printer-side one-liner because
   *  it needs interactive root the GUI can't run. */
  service_install?: string
  /** Human note explaining what `service_install` adds (shown above the command). */
  service_install_hint?: string
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
  /** For an installed first-party nginx app: whether it actually responds on its port right now. */
  running?: boolean
}

export interface SetupStatus {
  /** component id → its install state, versions and update flag. */
  status: Record<string, SetupComponentStatus>
  /** Whether GUI install/update/remove is enabled on this host. */
  writesEnabled: boolean
  /** The one-line command that installs the whole FilaMind suite. */
  suiteCommand: string
}

export interface SetupActionResult {
  ok?: boolean
  output?: string
}
