/** In-app feedback / issue reporting.
 *
 *  A single shared state drives three entry points — the header Feedback menu (bug / feature),
 *  and a small "Report" button on error surfaces — so any of them can open the same dialog. We
 *  never post anything on the user's behalf: submitting just opens a *pre-filled* GitHub
 *  `issues/new` form in a new tab for the user to review and submit themselves.
 *
 *  The diagnostics block and the issue body are intentionally **English**, regardless of the UI
 *  locale, so maintainers can act on every report. The dialog's own labels are localized.
 *
 *  Screenshots are best-effort and never block a report: html-to-image renders the current view,
 *  then we copy it to the clipboard where that's allowed (a secure context — https or localhost)
 *  and fall back to a file download on the plain-http LAN the printer is usually served over.
 */
import { reactive } from 'vue'

import { i18n } from './i18n'
import { useNav } from './nav'
import { widgetRegistry } from './registry'
import { currentTheme } from './theme'

/** The project's own repository — issues are opened here. */
const REPO = 'filamind-app/filamind-flow'

export type ReportMode = 'bug' | 'feature'
export type ScreenshotMethod = 'clipboard' | 'download' | 'failed' | 'none' | ''

export interface Diagnostics {
  version: string
  view: string
  locale: string
  theme: string
  screen: string
  userAgent: string
  time: string
}

interface FeedbackState {
  open: boolean
  mode: ReportMode
  /** `form` while composing, `sent` after the issue tab is opened. */
  phase: 'form' | 'sent'
  /** Pre-filled error text when launched from a "Report this error" button. */
  errorText: string
  attachScreenshot: boolean
  capturing: boolean
  screenshot: Blob | null
  /** Object URL for the dialog thumbnail; revoked on close. */
  screenshotUrl: string | null
  screenshotMethod: ScreenshotMethod
  sending: boolean
}

export const feedback = reactive<FeedbackState>({
  open: false,
  mode: 'bug',
  phase: 'form',
  errorText: '',
  attachScreenshot: true,
  capturing: false,
  screenshot: null,
  screenshotUrl: null,
  screenshotMethod: '',
  sending: false,
})

const { current } = useNav()

/** The English title of the active widget (or "Dashboard") — for the diagnostics, not the UI. */
function activeViewLabel(): string {
  const id = current.value
  if (!id || id === 'dashboard') return 'Dashboard'
  return widgetRegistry.get(id)?.title ?? id
}

export function collectDiagnostics(): Diagnostics {
  return {
    version: typeof __APP_VERSION__ !== 'undefined' ? __APP_VERSION__ : 'unknown',
    view: activeViewLabel(),
    locale: String(i18n.global.locale.value),
    theme: currentTheme.value,
    screen: `${window.screen?.width ?? window.innerWidth}×${window.screen?.height ?? window.innerHeight}`,
    userAgent: navigator.userAgent,
    time: new Date().toISOString(),
  }
}

// --- screenshot ------------------------------------------------------------

/** Render the current view to a PNG blob, excluding the feedback UI itself. Best-effort: any
 *  failure (unsupported, tainted canvas, missing lib) resolves to null and the report proceeds. */
async function captureScreenshot(): Promise<Blob | null> {
  try {
    const { toBlob } = await import('html-to-image')
    const target = document.getElementById('app') ?? document.body
    const bg = getComputedStyle(target).backgroundColor
    return await toBlob(target, {
      backgroundColor: !bg || bg === 'rgba(0, 0, 0, 0)' ? '#ffffff' : bg,
      pixelRatio: Math.min(window.devicePixelRatio || 1, 2),
      // Skip web-font inlining: the fonts come from a cross-origin stylesheet (Google Fonts) whose
      // cssRules can't be read, so embedding always fails anyway — skipping it avoids a burst of
      // SecurityError console noise and speeds up capture (the rasterised text is unaffected).
      skipFonts: true,
      // Drop the feedback dialog / menu so the shot shows the app, not the report UI.
      filter: (node) => !(node instanceof HTMLElement && 'feedbackNoshot' in node.dataset),
    })
  } catch {
    return null
  }
}

function downloadBlob(blob: Blob): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `filamind-report-${Date.now()}.png`
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 10000)
}

/** Put the screenshot where the user can attach it: the clipboard in a secure context, else a
 *  downloaded file. MUST be initiated from a user gesture (the submit click). */
async function deliverScreenshot(blob: Blob): Promise<Exclude<ScreenshotMethod, '' | 'none'>> {
  try {
    if (
      window.isSecureContext &&
      navigator.clipboard &&
      typeof window.ClipboardItem !== 'undefined'
    ) {
      await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })])
      return 'clipboard'
    }
  } catch {
    // Fall through to a download — e.g. clipboard permission denied.
  }
  try {
    downloadBlob(blob)
    return 'download'
  } catch {
    return 'failed'
  }
}

// --- actions ---------------------------------------------------------------

// Each capture gets a generation number; only the latest may write to the state. This stops a
// slow capture from a previous open() (or a closed dialog) from overwriting a newer screenshot.
let captureGen = 0

function setScreenshot(blob: Blob | null): void {
  if (feedback.screenshotUrl) URL.revokeObjectURL(feedback.screenshotUrl)
  feedback.screenshot = blob
  feedback.screenshotUrl = blob ? URL.createObjectURL(blob) : null
}

function resetScreenshot(): void {
  captureGen++ // invalidate any capture still in flight
  if (feedback.screenshotUrl) URL.revokeObjectURL(feedback.screenshotUrl)
  feedback.screenshot = null
  feedback.screenshotUrl = null
  feedback.screenshotMethod = ''
}

/** Open the report dialog. For bug reports a screenshot is captured in the background (the dialog
 *  shows a "capturing…" state) so it's ready by the time the user submits. */
export function openReport(mode: ReportMode, opts?: { error?: string }): void {
  resetScreenshot()
  feedback.mode = mode
  feedback.phase = 'form'
  feedback.errorText = opts?.error?.trim() ?? ''
  feedback.attachScreenshot = mode === 'bug'
  feedback.sending = false
  feedback.open = true

  if (mode === 'bug') {
    const gen = ++captureGen
    feedback.capturing = true
    void captureScreenshot()
      .then((blob) => {
        // Drop the result if a newer capture started or the dialog was closed/reopened meanwhile.
        if (gen !== captureGen || !feedback.open || feedback.mode !== 'bug') return
        setScreenshot(blob)
      })
      .finally(() => {
        if (gen === captureGen) feedback.capturing = false
      })
  } else {
    captureGen++ // invalidate any bug capture still in flight from a previous open
    feedback.capturing = false
  }
}

export function closeReport(): void {
  feedback.open = false
  feedback.sending = false
  resetScreenshot()
}

function buildTitle(description: string): string {
  const base =
    (feedback.errorText || description).trim().split('\n')[0].slice(0, 72).trim() || 'Report'
  return feedback.mode === 'bug' ? `[Bug] ${base}` : `[Feature] ${base}`
}

function buildBody(description: string): string {
  const d = collectDiagnostics()
  const lines: string[] = []
  lines.push(description.trim() || '_No description provided._')
  lines.push('')
  if (feedback.errorText) {
    lines.push('### Error message')
    lines.push('```')
    lines.push(feedback.errorText.slice(0, 1500))
    lines.push('```')
    lines.push('')
  }
  lines.push('### Diagnostics')
  lines.push(`- **App version:** ${d.version}`)
  lines.push(`- **Active view:** ${d.view}`)
  lines.push(`- **Language:** ${d.locale}`)
  lines.push(`- **Theme:** ${d.theme}`)
  lines.push(`- **Screen:** ${d.screen}`)
  lines.push(`- **Browser:** ${d.userAgent.slice(0, 300)}`)
  lines.push(`- **Time:** ${d.time}`)
  if (feedback.mode === 'bug' && feedback.attachScreenshot && feedback.screenshot) {
    lines.push('')
    lines.push(
      '_A screenshot was captured — paste it here with Ctrl/⌘+V, or drag in the downloaded image._',
    )
  }
  lines.push('')
  lines.push('<!-- Opened from FilaMind Flow → Feedback. Please review before submitting. -->')
  return lines.join('\n')
}

export function buildIssueUrl(description: string): string {
  const params = new URLSearchParams({
    title: buildTitle(description),
    body: buildBody(description),
    labels: feedback.mode === 'bug' ? 'bug' : 'enhancement',
  })
  return `https://github.com/${REPO}/issues/new?${params.toString()}`
}

/** Open the pre-filled issue in a new tab and deliver the screenshot. Call from the submit click
 *  (a user gesture) so the clipboard write / download and the popup are allowed. */
export function submitReport(description: string): void {
  feedback.sending = true
  const url = buildIssueUrl(description)

  // Initiate the screenshot delivery *before* opening the tab, both within this gesture so neither
  // the clipboard write nor the popup is blocked. We don't await before window.open.
  let delivery: Promise<ScreenshotMethod> | null = null
  if (feedback.mode === 'bug' && feedback.attachScreenshot && feedback.screenshot) {
    delivery = deliverScreenshot(feedback.screenshot)
  }

  window.open(url, '_blank', 'noopener,noreferrer')

  if (delivery) {
    void delivery.then((m) => {
      feedback.screenshotMethod = m
    })
  } else {
    feedback.screenshotMethod =
      feedback.mode === 'bug' && feedback.attachScreenshot ? 'failed' : 'none'
  }

  feedback.sending = false
  feedback.phase = 'sent'
}
