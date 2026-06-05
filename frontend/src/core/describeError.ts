/** Maps a raw fetch / HTTP failure to a clear, actionable message — never a bare "Failed to
 *  fetch". Shared so every widget degrades the same way when the backend is unreachable. */
export function describeError(e: unknown): string {
  const m = e instanceof Error ? e.message : String(e)
  if (/failed to fetch|networkerror|load failed|fetch/i.test(m)) {
    return 'Cannot reach the FilaMind backend — check that the filamind-flow service is running and reachable.'
  }
  return m
}
