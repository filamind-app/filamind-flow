/** Open a pre-filled GitHub issue for a Hardware Browser catalog submission.
 *
 *  Like the feedback flow, this NEVER posts on the user's behalf and uses no token — it only opens
 *  a pre-filled `issues/new` form in a new tab for the user to review and submit. A maintainer then
 *  validates the JSON fragment and merges it into the catalog (scripts/apply_submission.py). */

const REPO = 'filamind-app/filamind-flow'

export interface CatalogSubmission {
  /** Part type (motor, driver, hotend, …) — used in the title and label. */
  type: string
  /** Human title fragment, e.g. "LDO Motors 42STH48". */
  label: string
  /** The catalog-shaped JSON fragment to submit. */
  fragment: Record<string, unknown>
}

function buildBody(sub: CatalogSubmission): string {
  const version = typeof __APP_VERSION__ !== 'undefined' ? __APP_VERSION__ : 'unknown'
  const json = JSON.stringify(sub.fragment, null, 2)
  return [
    `### New catalog part — ${sub.type}`,
    '',
    `**${sub.label || '(unnamed)'}**`,
    '',
    'Proposed entry for the hardware catalog. A maintainer will review the data and, once',
    'confirmed, merge it into the catalog and rebuild the database.',
    '',
    '```json',
    json,
    '```',
    '',
    '<!-- Submitted from FilaMind Flow → Hardware Browser → Suggest a part.',
    `     App version: ${version}. Please review the fields before submitting. -->`,
  ].join('\n')
}

export function buildSubmissionUrl(sub: CatalogSubmission): string {
  const params = new URLSearchParams({
    title: `[Catalog] ${sub.type}: ${sub.label}`.slice(0, 120),
    body: buildBody(sub),
    labels: 'catalog-submission',
  })
  return `https://github.com/${REPO}/issues/new?${params.toString()}`
}

/** Open the pre-filled submission issue in a new tab. Call from a user gesture. */
export function openSubmission(sub: CatalogSubmission): void {
  window.open(buildSubmissionUrl(sub), '_blank', 'noopener,noreferrer')
}
