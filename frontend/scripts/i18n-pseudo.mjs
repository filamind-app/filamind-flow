#!/usr/bin/env node
// Dev aid: print a pseudo-localized copy of the `en` catalog (accented + ~40% wider + bracketed).
// Eyeball it to catch expansion/RTL overflow and to spot any hardcoded English that never made it
// into the catalog. Phase 0 prints to stdout; a later phase wires a live "pseudo" locale into the
// running app for in-browser eyeballing.
//
//   npm run i18n:pseudo            # whole en catalog, pseudo-localized
//   npm run i18n:pseudo -- shell   # just the `shell` namespace

import { readdirSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { pseudoizeTree } from './i18n-lib.mjs'

const enDir = join(dirname(fileURLToPath(import.meta.url)), '..', 'src', 'locales', 'en')

const en = {}
for (const file of readdirSync(enDir).filter((f) => f.endsWith('.json'))) {
  Object.assign(en, JSON.parse(readFileSync(join(enDir, file), 'utf8')))
}

const ns = process.argv[2]
const subject = ns ? { [ns]: en[ns] } : en
if (ns && en[ns] === undefined) {
  console.error(`i18n-pseudo: no namespace '${ns}' in the en catalog (have: ${Object.keys(en).join(', ')})`)
  process.exit(1)
}

console.log(JSON.stringify(pseudoizeTree(subject), null, 2))
