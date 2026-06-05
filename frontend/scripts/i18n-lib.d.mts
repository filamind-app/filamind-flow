// Types for the plain-ESM i18n helpers, so the TypeScript test (and `vue-tsc`) can import them.
// The runtime implementation lives in `i18n-lib.mjs`.

export function flattenKeys(obj: unknown, prefix?: string): string[]
export function diffKeys(
  referenceKeys: string[],
  localeKeys: string[],
): { missing: string[]; extra: string[] }
export function pseudoize(s: string): string
export function pseudoizeTree<T>(obj: T): T
