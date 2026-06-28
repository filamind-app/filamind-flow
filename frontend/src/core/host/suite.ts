// Runtime detection of whether the FilaMind suite (the FilaMind 3D interface) is present on this
// printer. The suite-exclusive widgets (SUITE_GATED in adapter.ts) render their install-required gate
// in the standalone Mainsail build UNTIL FilaMind 3D is detected installed - then they unlock and run
// normally. Their data is served by the flow backend (e.g. /api/material), so unlocking needs no
// round-trip to the 3D backend; detecting that FilaMind 3D is installed is enough.
import { computed, ref, type ComputedRef } from 'vue'

import { resolveEndpoints } from '@/core/moonraker'

import { isSuiteHost } from './adapter'

const threeDInstalled = ref(false)

/** True when the suite-gated widgets should render their real UI: either this IS the suite build, or
 *  FilaMind 3D is installed on the printer (detected at runtime via the setup status). */
export const suiteUnlocked: ComputedRef<boolean> = computed(
  () => isSuiteHost() || threeDInstalled.value,
)

interface SetupStatusShape {
  status?: Record<string, { status?: string } | undefined>
}

/**
 * Probe the flow backend's setup status and unlock the suite widgets if FilaMind 3D is installed.
 * Best-effort: any failure (offline, non-200, malformed) leaves the widgets gated - the safe default.
 */
export async function detectSuiteHost(
  fetchImpl: typeof fetch = typeof fetch !== 'undefined' ? fetch : (undefined as never),
): Promise<void> {
  if (isSuiteHost()) return // already unlocked by build; no probe needed
  try {
    const res = await fetchImpl(`${resolveEndpoints().backendUrl}/api/setup/status`)
    if (!res.ok) return
    const data = (await res.json()) as SetupStatusShape
    threeDInstalled.value = data.status?.['filamind-3d']?.status === 'installed'
  } catch {
    // leave gated
  }
}
