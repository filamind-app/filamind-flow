/** A saved known-good config pack (mirrors the backend). */
export interface KgpPack {
  id: string
  label: string
  /** Unix seconds when the pack was created. */
  created: number
  file_count: number
}

export interface KgpDetail extends KgpPack {
  files: string[]
}

export interface KgpRestoreResult {
  ok: boolean
  code: string
  params: Record<string, unknown>
}
