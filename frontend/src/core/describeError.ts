import { i18n } from './i18n'

/** Maps a raw fetch / HTTP failure to a clear, actionable message — never a bare "Failed to
 *  fetch". Shared so every widget degrades the same way when the backend is unreachable. The
 *  network-failure copy is translated; an upstream error's own text is passed through as-is. */
export function describeError(e: unknown): string {
  const m = e instanceof Error ? e.message : String(e)
  if (/failed to fetch|networkerror|load failed|fetch/i.test(m)) {
    return i18n.global.t('common.errors.backendUnreachable')
  }
  return m
}
