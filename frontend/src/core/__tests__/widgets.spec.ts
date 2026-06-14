import { readdirSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

/**
 * Non-negotiable widget conventions, enforced in CI so they can't be skipped (a prose rule in
 * CONTRIBUTING.md was being missed). Every registered widget MUST:
 *   1. have a translated sidebar entry — shell.widgets.<id>.{title,description} — so the sidebar
 *      never falls back to the raw English registry label; and
 *   2. render the shared <HelpDrawer> guide (the adopted help pattern), not an ad-hoc inline guide.
 * The 7-locale key-parity test (locales.spec.ts) then guarantees the sidebar entry exists in every
 * language too.
 */

const SRC = resolve(dirname(fileURLToPath(import.meta.url)), '../../') // .../frontend/src
const indexSrc = readFileSync(resolve(SRC, 'widgets/index.ts'), 'utf8')
const shellWidgets: Record<string, { title?: string; description?: string }> = JSON.parse(
  readFileSync(resolve(SRC, 'locales/en/shell.json'), 'utf8'),
).shell.widgets

// The registered widget ids, parsed from the registry source (no need to execute it).
const REGISTERED_IDS = [...indexSrc.matchAll(/id:\s*'([^']+)'/g)].map((m) => m[1])

/** True if any .vue in src/widgets/<id>/ pulls in the shared HelpDrawer. */
function usesHelpDrawer(id: string): boolean {
  const dir = resolve(SRC, 'widgets', id)
  return readdirSync(dir)
    .filter((f) => f.endsWith('.vue'))
    .some((f) => readFileSync(resolve(dir, f), 'utf8').includes('HelpDrawer'))
}

describe('widget conventions (enforced — do not bypass)', () => {
  it('discovered the registered widgets', () => {
    expect(REGISTERED_IDS.length).toBeGreaterThanOrEqual(12)
    expect(new Set(REGISTERED_IDS).size).toBe(REGISTERED_IDS.length) // ids are unique
  })

  for (const id of REGISTERED_IDS) {
    it(`${id}: has a translated sidebar entry (shell.widgets.${id})`, () => {
      const entry = shellWidgets[id]
      expect(
        entry,
        `Missing shell.widgets.${id} — add { title, description } to every locale's shell.json so the sidebar isn't an English fallback.`,
      ).toBeTruthy()
      expect(entry.title ?? '').not.toHaveLength(0)
      expect(entry.description ?? '').not.toHaveLength(0)
    })

    it(`${id}: renders the shared <HelpDrawer> guide`, () => {
      expect(
        usesHelpDrawer(id),
        `Widget '${id}' must use the shared <HelpDrawer> guide (the adopted help pattern) — not an ad-hoc <details>/inline note.`,
      ).toBe(true)
    })
  }
})
