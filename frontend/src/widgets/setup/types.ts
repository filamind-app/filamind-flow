export interface SetupComponent {
  id: string
  name: string
  kind: string
  repo: string
  type: string
  deps?: string[]
  first_party?: boolean
}

export interface SetupGroup {
  group: string
  components: SetupComponent[]
}

export interface SetupCatalog {
  schema: number
  groups: SetupGroup[]
}

export interface SetupStatus {
  /** component id → 'installed' | 'not-installed' (best-effort). */
  status: Record<string, string>
  /** Whether GUI install/update/remove is enabled on this host. */
  writesEnabled: boolean
}

export interface SetupActionResult {
  ok?: boolean
  output?: string
}
