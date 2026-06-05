#!/usr/bin/env node
// CI gate: every non-reference locale must carry EXACTLY the `en` key set — no missing, no extra.
// This replaces eslint's `no-unused-keys`, which is unreliable here because keys are built
// dynamically (e.g. `t('inputShaping.grade.verdict.' + letter)`). With only `en` present (Phase 0)
// it is a trivial pass; it starts doing real work the moment a second locale lands.

import { readdirSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { diffKeys, flattenKeys } from './i18n-lib.mjs'

const localesDir = join(dirname(fileURLToPath(import.meta.url)), '..', 'src', 'locales')
const REFERENCE = 'en'

/** Merge every namespace JSON in a locale folder into one message object. */
function loadLocale(code) {
  const dir = join(localesDir, code)
  const merged = {}
  for (const file of readdirSync(dir).filter((f) => f.endsWith('.json'))) {
    Object.assign(merged, JSON.parse(readFileSync(join(dir, file), 'utf8')))
  }
  return merged
}

const codes = readdirSync(localesDir, { withFileTypes: true })
  .filter((d) => d.isDirectory())
  .map((d) => d.name)

if (!codes.includes(REFERENCE)) {
  console.error(`i18n-keydiff: no reference locale '${REFERENCE}' under ${localesDir}`)
  process.exit(1)
}

const refKeys = flattenKeys(loadLocale(REFERENCE))
const others = codes.filter((c) => c !== REFERENCE)
let failed = false

for (const code of others) {
  const { missing, extra } = diffKeys(refKeys, flattenKeys(loadLocale(code)))
  if (missing.length || extra.length) {
    failed = true
    console.error(`✗ ${code}: ${missing.length} missing, ${extra.length} extra key(s) vs ${REFERENCE}`)
    for (const k of missing) console.error(`    missing: ${k}`)
    for (const k of extra) console.error(`    extra:   ${k}`)
  } else {
    console.log(`✓ ${code}: ${refKeys.length} keys match ${REFERENCE}`)
  }
}

if (!others.length) {
  console.log(`i18n-keydiff: only '${REFERENCE}' present (${refKeys.length} keys) — nothing to diff yet.`)
}

process.exit(failed ? 1 : 0)
