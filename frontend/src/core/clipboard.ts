/** Clipboard helper that also works on a plain-http LAN host.
 *
 *  On the printer the panel is served over http (e.g. http://192.168.0.59), which is NOT a
 *  secure context, so `navigator.clipboard` is undefined. Calling it there throws - which is
 *  why a bare `navigator.clipboard.writeText(...)` surfaced as a copy error on the printer.
 *  This falls back to the legacy `document.execCommand('copy')` path in that case.
 *
 *  Returns true when the text was placed on the clipboard, false otherwise (callers can show
 *  a "copied" tick or an error without try/catch).
 */
export async function copyText(text: string): Promise<boolean> {
  try {
    if (window.isSecureContext && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    // fall through to the legacy path
  }
  try {
    const ta = document.createElement('textarea')
    ta.value = text
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(ta)
    return ok
  } catch {
    return false
  }
}
