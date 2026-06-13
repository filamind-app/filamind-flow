/** Webcam helpers for the Max-Flow widget. The backend proxies the host's snapshot so the
 *  browser loads it same-origin (the panel's nginx doesn't expose the host `/webcam/` path). */
import { resolveEndpoints } from '@/core/moonraker'

export interface CameraInfo {
  name: string
  service: string
}

/** Configured webcams (empty when none, Moonraker is unreachable, or the request fails). */
export async function fetchCameras(): Promise<CameraInfo[]> {
  const { backendUrl } = resolveEndpoints()
  try {
    const response = await fetch(`${backendUrl}/api/camera/list`)
    if (!response.ok) return []
    return ((await response.json()) as { cameras?: CameraInfo[] }).cameras ?? []
  } catch {
    return []
  }
}

/** A cache-busted snapshot URL for `<img>`; pass a monotonically rising `tick` to force reloads. */
export function snapshotUrl(name: string | undefined, tick: number): string {
  const { backendUrl } = resolveEndpoints()
  const query = new URLSearchParams()
  if (name) query.set('name', name)
  query.set('t', String(tick))
  return `${backendUrl}/api/camera/snapshot?${query.toString()}`
}
