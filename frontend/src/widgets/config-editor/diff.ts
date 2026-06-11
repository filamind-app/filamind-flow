/** Minimal line-level diff (LCS) for the Config Editor backup timeline. Dependency-free.
 *
 * `diffLines(a, b)` returns one row per line: `eq` (unchanged), `del` (in `a` only — removed by
 * going a→b) or `add` (in `b` only — added by going a→b). `collapseDiff` folds long runs of
 * unchanged lines into a single marker so a near-identical file shows only what actually changed. */

export type DiffKind = 'eq' | 'add' | 'del'
export interface DiffRow {
  kind: DiffKind
  text: string
}

/** Largest line count this runs the O(n·m) LCS on; bigger inputs fall back to a coarse diff. */
const MAX_LCS_LINES = 4000

function coarseDiff(a: string[], b: string[]): DiffRow[] {
  // For very large inputs, skip the quadratic LCS: show all removals then all additions.
  const bset = new Set(b)
  const aset = new Set(a)
  const rows: DiffRow[] = []
  for (const line of a) if (!bset.has(line)) rows.push({ kind: 'del', text: line })
  for (const line of b) if (!aset.has(line)) rows.push({ kind: 'add', text: line })
  return rows
}

/** Diff two texts line-by-line. `a` is the baseline (current), `b` the comparison (backup). */
export function diffLines(aText: string, bText: string): DiffRow[] {
  const a = aText.split('\n')
  const b = bText.split('\n')
  if (a.length > MAX_LCS_LINES || b.length > MAX_LCS_LINES) return coarseDiff(a, b)

  const n = a.length
  const m = b.length
  // dp[i][j] = LCS length of a[i:] and b[j:]
  const dp: number[][] = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0))
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1])
    }
  }
  const rows: DiffRow[] = []
  let i = 0
  let j = 0
  while (i < n && j < m) {
    if (a[i] === b[j]) {
      rows.push({ kind: 'eq', text: a[i] })
      i++
      j++
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      rows.push({ kind: 'del', text: a[i] })
      i++
    } else {
      rows.push({ kind: 'add', text: b[j] })
      j++
    }
  }
  while (i < n) rows.push({ kind: 'del', text: a[i++] })
  while (j < m) rows.push({ kind: 'add', text: b[j++] })
  return rows
}

export interface CollapsedRow extends DiffRow {
  /** Set on a synthetic `eq` marker that stands in for `hidden` unchanged lines. */
  hidden?: number
}

/** Fold runs of more than `context`·2 unchanged rows into a single marker, keeping `context` lines
 *  of surrounding context so each change stays readable. */
export function collapseDiff(rows: DiffRow[], context = 2): CollapsedRow[] {
  const out: CollapsedRow[] = []
  let i = 0
  while (i < rows.length) {
    if (rows[i].kind !== 'eq') {
      out.push(rows[i])
      i++
      continue
    }
    let j = i
    while (j < rows.length && rows[j].kind === 'eq') j++
    const run = j - i
    if (run > context * 2 + 1) {
      const head = out.length > 0 ? context : 0 // no leading context at the very top
      for (let k = 0; k < head; k++) out.push(rows[i + k])
      out.push({ kind: 'eq', text: '', hidden: run - head - (j < rows.length ? context : 0) })
      const tail = j < rows.length ? context : 0
      for (let k = 0; k < tail; k++) out.push(rows[j - tail + k])
    } else {
      for (let k = i; k < j; k++) out.push(rows[k])
    }
    i = j
  }
  return out
}

/** Quick change summary: how many lines were added / removed (ignoring unchanged). */
export function diffStats(rows: DiffRow[]): { added: number; removed: number } {
  let added = 0
  let removed = 0
  for (const r of rows) {
    if (r.kind === 'add') added++
    else if (r.kind === 'del') removed++
  }
  return { added, removed }
}
