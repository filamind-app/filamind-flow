/** Beacon probe version helpers.
 *
 * A Beacon probe reports its RUNNING firmware version from its USB descriptor (always a bare
 * ``X.Y.Z``), while the newest AVAILABLE version comes from the plugin checkout's tags, which may
 * carry a ``v`` prefix or trailing detail. These pure helpers pull the comparable ``X.Y.Z`` core
 * out of either form so a freshly-flashed probe correctly reports "up to date" instead of forever
 * offering a Flash button.
 */

/** The comparable ``X.Y.Z`` core of a version string, or ``''`` if it has no numeric version part.
 *  A two-part ``X.Y`` is normalised to ``X.Y.0`` so it matches the probe's three-part report. */
export function beaconVerCore(v: string | null | undefined): string {
  const m = /(\d+)\.(\d+)(?:\.(\d+))?/.exec(v ?? '')
  return m ? `${m[1]}.${m[2]}.${m[3] ?? '0'}` : ''
}

/** Order two ``X.Y.Z`` cores numerically: negative if a < b, 0 if equal, positive if a > b. */
function compareVerCore(a: string, b: string): number {
  const pa = a.split('.').map(Number)
  const pb = b.split('.').map(Number)
  for (let i = 0; i < 3; i++) {
    const diff = (pa[i] ?? 0) - (pb[i] ?? 0)
    if (diff !== 0) return diff
  }
  return 0
}

/** True when the probe's running version is AT OR AHEAD OF the newest one the plugin offers - only a
 *  probe that is genuinely behind needs a flash. It must be ">=", not "==": the plugin's newest git
 *  tag can lag the firmware actually shipped on its HEAD (the flasher uses HEAD), so a probe often
 *  runs a version higher than the newest tag - reporting that as "needs flash" was the #610 bug.
 *  Both versions must be known; an unreadable probe or a missing plugin tag falls back to Flash. */
export function beaconUpToDate(
  current: string | null | undefined,
  available: string | null | undefined,
): boolean {
  const cur = beaconVerCore(current)
  const avail = beaconVerCore(available)
  return cur !== '' && avail !== '' && compareVerCore(cur, avail) >= 0
}
