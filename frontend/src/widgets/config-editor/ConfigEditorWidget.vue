<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import ComboSelect from '@/components/ui/ComboSelect.vue'
import HelpDrawer from '@/components/ui/HelpDrawer.vue'
import WidgetTabs from '@/components/ui/WidgetTabs.vue'
import { describeError } from '@/core/describeError'
import { useNav } from '@/core/nav'
import {
  fetchBoardDetail,
  fetchDriverDetail,
  fetchMotorDetail,
} from '@/widgets/hardware-browser/api'
import HardwarePicker from '@/widgets/hardware-browser/HardwarePicker.vue'
import { useEntityFocus } from '@/widgets/hardware-browser/useEntityFocus'

import {
  adoptParam,
  ApiError,
  fetchBackupContent,
  fetchBackups,
  fetchConfigDrift,
  fetchConfigFile,
  fetchConfigFiles,
  fetchConfigGraph,
  fetchConfigSanity,
  fetchFieldPolicy,
  fetchPinDoctor,
  fetchPinMap,
  restartFirmware,
  saveConfigFile,
  searchConfig,
} from './api'
import { collapseDiff, type CollapsedRow, diffLines, diffStats } from './diff'
import HelpIllo from './HelpIllo.vue'
import { GLOSSARY_KEYS, HELP_ILLO, HELP_TOPICS } from './help'
import type {
  ConfigBackup,
  ConfigBackupList,
  ConfigDrift,
  ConfigDriftResult,
  ConfigFileInfo,
  ConfigFileView,
  ConfigGraph,
  ConfigParamView,
  ConfigSanityFinding,
  ConfigSanityResult,
  ConfigSearchResult,
  ConfigSectionView,
  FieldPolicyEntry,
  PinDoctorResult,
  PinMapMcu,
  PinMapResult,
} from './types'

const { t, te } = useI18n({ useScope: 'global' })
const { go } = useNav()
const { focusEntity } = useEntityFocus()

const files = ref<ConfigFileInfo[]>([])
const selected = ref<string | null>(null)
const view = ref<ConfigFileView | null>(null)
const loadingFiles = ref(true)
const loadingView = ref(false)
const errFiles = ref<string | null>(null)
const errView = ref<string | null>(null)
const viewMode = ref<'structured' | 'raw'>('structured')
/** Per-section disclosure (keyed by index, since headers can repeat — e.g. duplicate sections). */
const open = ref<Record<number, boolean>>({})

// Edit / save / restart state (the gated write path lives in the Raw view).
const draft = ref('')
const saving = ref(false)
const restarting = ref(false)
const confirmMode = ref<null | 'save' | 'restart'>(null)
const ack = ref(false)
const saveMsg = ref<string | null>(null)
const saveErr = ref<string | null>(null)
const restartMsg = ref<string | null>(null)
const restartErr = ref<string | null>(null)
const showRestartPrompt = ref(false)

const dirty = computed(() => view.value != null && draft.value !== view.value.raw)

// Disk-vs-live drift: compare the file to what Klipper is actually running.
const drift = ref<ConfigDriftResult | null>(null)
const adopting = ref<string | null>(null)
const hasLiveInfo = computed(() => {
  const d = drift.value
  return (
    !!d && d.reachable && (d.save_config_pending || d.warnings.length > 0 || d.drifts.length > 0)
  )
})

async function loadDrift(filename: string): Promise<void> {
  try {
    drift.value = await fetchConfigDrift(filename)
  } catch {
    drift.value = null
  }
}

// Whole-config pin doctor (double-assigned pins + electronics caveats across every MCU).
const pinDoctor = ref<PinDoctorResult | null>(null)
async function loadPinDoctor(): Promise<void> {
  try {
    pinDoctor.value = await fetchPinDoctor()
  } catch {
    pinDoctor.value = null
  }
}

// Driver value sanity: run_current vs the driver ceiling / mapped-motor rating + microsteps.
const sanity = ref<ConfigSanityResult | null>(null)
async function loadSanity(): Promise<void> {
  try {
    sanity.value = await fetchConfigSanity()
  } catch {
    sanity.value = null
  }
}
function sanityMsg(f: ConfigSanityFinding): string {
  return t('configEditor.sanity.rule.' + f.rule, { section: f.section, ...f.detail })
}

// Typed editing for TMC register fields: per-model field policy (control + mask-derived range).
const policies = ref<Record<string, Record<string, FieldPolicyEntry>>>({})
async function ensurePolicy(model: string): Promise<void> {
  if (!model.toLowerCase().startsWith('tmc') || policies.value[model]) return
  try {
    const r = await fetchFieldPolicy(model)
    policies.value = { ...policies.value, [model]: r.fields }
  } catch {
    /* no policy for this model — params stay plain text */
  }
}
function policyFor(sectionType: string, key: string): FieldPolicyEntry | null {
  const m = policies.value[sectionType]
  if (!m) return null
  return m[key.toLowerCase().replace(/^driver_/, '')] ?? null
}
function rangeHint(p: FieldPolicyEntry): string {
  if (p.enum) return p.enum.join(' / ')
  if (p.velocity) return 'mm/s ≥ 0'
  if (p.min != null && p.max != null) return `${p.min}…${p.max}`
  return ''
}
function clampNum(p: FieldPolicyEntry, value: string): string {
  const n = Number(value)
  if (Number.isNaN(n)) return value
  let v = n
  if (p.min != null) v = Math.max(p.min, v)
  if (p.max != null) v = Math.min(p.max, v)
  if (p.velocity) v = Math.max(0, v)
  return String(v)
}
async function onTmcEdit(
  section: ConfigSectionView,
  param: ConfigParamView,
  value: string,
): Promise<void> {
  param.value = value
  try {
    draft.value = await adoptParam(draft.value, section.header, param.key, value)
  } catch (e) {
    saveErr.value = describeError(e)
  }
}

// Pin-aware editing: for any `*_pin` param, map the value's chip prefix to its MCU's resolved
// board, then offer that board's named pins as suggestions and flag an off-board / double-assigned
// / electronics-caveat pin inline. Edits ride the same surgical round-trip as the TMC controls.
const pinMap = ref<PinMapResult | null>(null)
async function loadPinMap(): Promise<void> {
  try {
    pinMap.value = await fetchPinMap()
  } catch {
    pinMap.value = null
  }
}
function isPinParam(p: ConfigParamView): boolean {
  const k = p.key.toLowerCase()
  return k === 'pin' || k.endsWith('_pin')
}
/** Split a Klipper pin value into its `chip:` prefix (or 'mcu' when bare) and the bare pin name. */
function splitPin(value: string): { chip: string; pin: string } {
  const v = value.trim().replace(/^[\^~!]+/, '')
  const i = v.indexOf(':')
  if (i >= 0) {
    const pin = v
      .slice(i + 1)
      .replace(/^[\^~!]+/, '')
      .trim()
    return { chip: v.slice(0, i).trim(), pin: pin.toUpperCase() }
  }
  return { chip: 'mcu', pin: v.toUpperCase() }
}
function mcuForPin(value: string): PinMapMcu | null {
  if (!pinMap.value?.reachable) return null
  const { chip } = splitPin(value)
  const mcus = pinMap.value.mcus
  const exact = mcus.find((m) => m.name === chip)
  if (exact) return exact
  return chip === 'mcu' ? (mcus.find((m) => m.name === 'mcu') ?? mcus[0] ?? null) : null
}
/** Valid full-form pin strings for this param's MCU, preserving its `chip:` prefix convention. */
function pinOptions(value: string): string[] {
  const mcu = mcuForPin(value)
  if (!mcu) return []
  const { chip } = splitPin(value)
  const prefix = chip === 'mcu' ? '' : `${chip}:`
  return mcu.pins.map((p) => prefix + p.pin)
}
/** Inline flags for a pin value: not on the board map, double-assigned, or carries a caveat. */
function pinFlags(value: string): {
  offBoard: boolean
  doubleAssign: boolean
  caveat: string | null
} {
  const mcu = mcuForPin(value)
  const { pin } = splitPin(value)
  if (!mcu || !pin || mcu.pins.length === 0) {
    return { offBoard: false, doubleAssign: false, caveat: null }
  }
  const info = mcu.pins.find((p) => p.pin.toUpperCase() === pin)
  if (!info) return { offBoard: true, doubleAssign: false, caveat: null }
  return { offBoard: false, doubleAssign: info.owners.length > 1, caveat: info.caveat }
}

// Project view: the `[include]` dependency graph + cross-file lint, and project-wide search.
const graph = ref<ConfigGraph | null>(null)
async function loadGraph(): Promise<void> {
  try {
    graph.value = await fetchConfigGraph()
  } catch {
    graph.value = null
  }
}
/** Flatten the include graph into indented rows (DFS from each root; cycle-guarded). */
const treeRows = computed<{ file: string; depth: number; broken: boolean }[]>(() => {
  const g = graph.value
  if (!g) return []
  const byFile = new Map(g.nodes.map((n) => [n.file, n]))
  const rows: { file: string; depth: number; broken: boolean }[] = []
  const expanded = new Set<string>()
  const walk = (file: string, depth: number): void => {
    rows.push({ file, depth, broken: false })
    const node = byFile.get(file)
    if (!node || expanded.has(file)) return
    expanded.add(file)
    for (const m of node.missing) rows.push({ file: m, depth: depth + 1, broken: true })
    for (const inc of node.includes) walk(inc, depth + 1)
  }
  for (const r of g.roots) walk(r, 0)
  // Files not reachable from any root (e.g. an unincluded standalone) — list them flat.
  for (const n of g.nodes) if (!expanded.has(n.file) && !g.roots.includes(n.file)) walk(n.file, 0)
  return rows
})
function ruleLabel(rule: string): string {
  const key = `configEditor.project.rule.${rule}`
  const label = t(key)
  return label === key ? rule : label
}
/** Number of actionable findings (errors + warnings) — informational overrides don't count. */
const lintActionable = computed(
  () => graph.value?.lint.filter((l) => l.level !== 'info').length ?? 0,
)
function lintClass(level: string): string {
  if (level === 'error') return 'bg-brand-red/10'
  if (level === 'warning') return 'bg-brand-yellow/20'
  return 'bg-ink/5'
}

const searchQuery = ref('')
const searchResult = ref<ConfigSearchResult | null>(null)
const searching = ref(false)
async function runSearch(): Promise<void> {
  const q = searchQuery.value.trim()
  if (!q) {
    searchResult.value = null
    return
  }
  searching.value = true
  try {
    searchResult.value = await searchConfig(q)
  } catch {
    searchResult.value = null
  } finally {
    searching.value = false
  }
}
/** Jump to a file from the tree / a search hit / a lint finding (loads it into the editor). */
function openFile(path: string, raw = false): void {
  if (files.value.some((f) => f.path === path)) {
    selected.value = path
    if (raw) viewMode.value = 'raw'
  }
}

// Inline knowledge: a short, plain-language blurb under each section + a deep-link to the catalog
// entity for a driver section. Knowledge is keyed by section type, with a few family fallbacks.
function knowledgeKey(type: string): string | null {
  const ty = type.toLowerCase()
  const direct = `configEditor.knowledge.${ty}`
  if (te(direct)) return direct
  if (ty.startsWith('tmc')) return 'configEditor.knowledge.tmc'
  if (ty.startsWith('stepper_')) return 'configEditor.knowledge.stepper'
  if (ty === 'bltouch' || ty.endsWith('_probe') || ty.startsWith('probe_'))
    return 'configEditor.knowledge.probe'
  if (ty === 'heater_fan' || ty === 'controller_fan' || ty === 'temperature_fan') {
    return te(`configEditor.knowledge.${ty}`) ? `configEditor.knowledge.${ty}` : null
  }
  return null
}
function sectionBlurb(type: string): string | null {
  const k = knowledgeKey(type)
  return k ? t(k) : null
}
/** The driver model id for a `[tmcXXXX …]` section (matches the catalog `driver_id`), else null. */
function tmcModel(type: string): string | null {
  return type.toLowerCase().startsWith('tmc') ? type.toLowerCase() : null
}
/** Deep-link into the Hardware Browser, focused on this driver's catalog entity. */
function openDriverInBrowser(model: string): void {
  focusEntity({ tab: 'drivers', id: model, name: model.toUpperCase() })
  go('hardware-browser')
}

// Backup timeline: every gated save snapshots the previous file under filamind-backups/. List them
// here, diff a snapshot against the current draft, and restore one by loading it into the editor
// (the restore then rides the same gated save, which snapshots the current file first).
const backups = ref<ConfigBackupList | null>(null)
async function loadBackups(filename: string): Promise<void> {
  backups.value = null
  try {
    backups.value = await fetchBackups(filename)
  } catch {
    backups.value = null
  }
}
const diffPath = ref<string | null>(null)
const diffRows = ref<CollapsedRow[]>([])
const diffSummary = ref<{ added: number; removed: number } | null>(null)
const backupBusy = ref<string | null>(null)

async function toggleDiff(b: ConfigBackup): Promise<void> {
  if (diffPath.value === b.path) {
    diffPath.value = null
    return
  }
  backupBusy.value = b.path
  try {
    const content = await fetchBackupContent(b.path)
    const rows = diffLines(draft.value, content) // current (draft) → backup
    diffSummary.value = diffStats(rows)
    diffRows.value = collapseDiff(rows, 2)
    diffPath.value = b.path
  } catch (e) {
    saveErr.value = describeError(e)
  } finally {
    backupBusy.value = null
  }
}

/** Restore a snapshot by loading it into the editor (Raw view) — the user then saves through the
 *  existing confirm gate, which backs up the current file first. */
async function restoreBackup(b: ConfigBackup): Promise<void> {
  backupBusy.value = b.path
  try {
    draft.value = await fetchBackupContent(b.path)
    viewMode.value = 'raw'
    diffPath.value = null
    saveMsg.value = null
  } catch (e) {
    saveErr.value = describeError(e)
  } finally {
    backupBusy.value = null
  }
}

async function adoptLive(d: ConfigDrift): Promise<void> {
  adopting.value = d.section + '|' + d.key
  try {
    draft.value = await adoptParam(draft.value, d.section, d.key, d.live)
    viewMode.value = 'raw'
  } catch (e) {
    saveErr.value = describeError(e)
  } finally {
    adopting.value = null
  }
}

// Insert-from-Catalog: pick a driver / motor / board and append its verbatim, hardware-accurate
// Klipper config block (run_current / sense_resistor / real pin names) to the draft for review.
const catalogType = ref<'drivers' | 'motors' | 'boards'>('drivers')
const catalogPick = ref<string | null>(null)
const inserting = ref(false)
const insertMsg = ref<string | null>(null)
const insertErr = ref(false)

const CATALOG_TABS = computed<{ id: 'drivers' | 'motors' | 'boards'; label: string }[]>(() => [
  { id: 'drivers', label: t('configEditor.catalog.drivers') },
  { id: 'motors', label: t('configEditor.catalog.motors') },
  { id: 'boards', label: t('configEditor.catalog.boards') },
])

async function onCatalogPick(id: string | null): Promise<void> {
  if (!id) return
  inserting.value = true
  insertMsg.value = null
  insertErr.value = false
  try {
    let snippet = ''
    let label = id
    if (catalogType.value === 'drivers') {
      const d = await fetchDriverDetail(id)
      snippet = d.configSnippet ?? ''
      label = d.name ?? id
    } else if (catalogType.value === 'motors') {
      const m = await fetchMotorDetail(id)
      snippet = m.configSnippet ?? ''
      label = m.name ?? id
    } else {
      const b = await fetchBoardDetail(id)
      snippet = b.configSnippet ?? ''
      label = b.display_name ?? b.model ?? id
    }
    if (snippet.trim()) {
      const base = draft.value.trimEnd()
      draft.value = base ? `${base}\n\n${snippet.trim()}\n` : `${snippet.trim()}\n`
      viewMode.value = 'raw'
      insertMsg.value = t('configEditor.catalog.inserted', { name: label })
    } else {
      insertErr.value = true
      insertMsg.value = t('configEditor.catalog.noSnippet', { name: label })
    }
  } catch (e) {
    insertErr.value = true
    insertMsg.value = describeError(e)
  } finally {
    inserting.value = false
    catalogPick.value = null
  }
}

const VIEW_TABS = computed<{ id: 'structured' | 'raw'; label: string }[]>(() => [
  { id: 'structured', label: t('configEditor.view.structured') },
  { id: 'raw', label: t('configEditor.view.raw') },
])

const fileOptions = computed(() =>
  files.value.map((f) => ({
    value: f.path,
    label: f.path,
    sublabel:
      f.size != null ? t('configEditor.summary.size', { kb: (f.size / 1024).toFixed(1) }) : '',
  })),
)

const paramTotal = computed(() =>
  (view.value?.sections ?? []).reduce((n, s) => n + s.params.length, 0),
)
const errorCount = computed(
  () => (view.value?.issues ?? []).filter((i) => i.level === 'error').length,
)
const warningCount = computed(
  () => (view.value?.issues ?? []).filter((i) => i.level === 'warning').length,
)

async function loadFiles(): Promise<void> {
  loadingFiles.value = true
  try {
    const list = await fetchConfigFiles()
    files.value = list.files
    errFiles.value = null
    // Default to printer.cfg when present, else the first file.
    const printerCfg = list.files.find((f) => f.path === 'printer.cfg')
    selected.value = printerCfg?.path ?? list.files[0]?.path ?? null
  } catch (e) {
    errFiles.value = describeError(e)
  } finally {
    loadingFiles.value = false
  }
}

async function loadView(filename: string): Promise<void> {
  loadingView.value = true
  drift.value = null
  try {
    const v = await fetchConfigFile(filename)
    view.value = v
    draft.value = v.raw
    errView.value = null
    open.value = {}
    void loadDrift(filename)
    void loadBackups(filename)
  } catch (e) {
    errView.value = describeError(e)
    view.value = null
    draft.value = ''
  } finally {
    loadingView.value = false
  }
}

function toggleSection(i: number, type: string): void {
  open.value[i] = !open.value[i]
  if (open.value[i]) void ensurePolicy(type)
}
function expandAll(): void {
  const next: Record<number, boolean> = {}
  ;(view.value?.sections ?? []).forEach((s, i) => {
    next[i] = true
    void ensurePolicy(s.type)
  })
  open.value = next
}
function collapseAll(): void {
  open.value = {}
}

function resetWriteState(): void {
  confirmMode.value = null
  ack.value = false
  saveMsg.value = null
  saveErr.value = null
  restartMsg.value = null
  restartErr.value = null
  showRestartPrompt.value = false
}

function revert(): void {
  if (view.value) draft.value = view.value.raw
}

function openSaveConfirm(): void {
  ack.value = false
  saveErr.value = null
  confirmMode.value = 'save'
}
function openRestartConfirm(): void {
  restartErr.value = null
  confirmMode.value = 'restart'
}
function cancelConfirm(): void {
  confirmMode.value = null
}

async function doSave(): Promise<void> {
  if (!selected.value) return
  saving.value = true
  saveErr.value = null
  saveMsg.value = null
  try {
    const res = await saveConfigFile(selected.value, draft.value)
    confirmMode.value = null
    await loadView(selected.value) // reload → draft resets to the saved content (dirty = false)
    saveMsg.value = t('configEditor.save.done', { backup: res.backup ?? '—' })
    showRestartPrompt.value = true
  } catch (e) {
    confirmMode.value = null
    saveErr.value =
      e instanceof ApiError && e.status === 409 ? t('configEditor.save.busy') : describeError(e)
  } finally {
    saving.value = false
  }
}

async function doRestart(): Promise<void> {
  restarting.value = true
  restartErr.value = null
  restartMsg.value = null
  try {
    await restartFirmware()
    confirmMode.value = null
    showRestartPrompt.value = false
    restartMsg.value = t('configEditor.restart.done')
  } catch (e) {
    confirmMode.value = null
    restartErr.value =
      e instanceof ApiError && e.status === 409 ? t('configEditor.restart.busy') : describeError(e)
  } finally {
    restarting.value = false
  }
}

watch(selected, (f) => {
  resetWriteState()
  if (f) void loadView(f)
})
onMounted(() => {
  void loadFiles()
  void loadPinDoctor()
  void loadPinMap()
  void loadGraph()
  void loadSanity()
})
</script>

<template>
  <div class="space-y-3 text-sm">
    <!-- Intro + help layer -->
    <div class="flex items-start justify-between gap-2">
      <p class="min-w-0 flex-1 text-xs opacity-70">{{ t('configEditor.intro') }}</p>
      <div class="flex shrink-0 items-center gap-2">
        <HelpDrawer
          namespace="configEditor"
          :topics="HELP_TOPICS"
          :illo-map="HELP_ILLO"
          :illo="HelpIllo"
          :glossary-keys="GLOSSARY_KEYS"
          steps-key="configEditor.help.steps"
          :button-label="t('configEditor.help.guide')"
          :title="t('configEditor.help.guideTitle')"
          :close-label="t('configEditor.help.close')"
          :steps-title="t('configEditor.help.howToRead')"
        />
        <HelpIllo illo="file" class="h-8 w-8 opacity-70" />
      </div>
    </div>

    <!-- File picker -->
    <div class="flex flex-wrap items-end gap-2">
      <label class="min-w-[12rem] flex-1">
        <span class="mb-1 block text-xs font-bold">{{ t('configEditor.file.label') }}</span>
        <ComboSelect
          v-model="selected"
          :options="fileOptions"
          :placeholder="t('configEditor.file.placeholder')"
          :disabled="loadingFiles || !!errFiles"
        />
      </label>
      <button
        class="nb-btn bg-surface px-2 py-1 text-xs"
        :disabled="loadingFiles"
        @click="loadFiles"
      >
        <span aria-hidden="true">↻</span> {{ t('configEditor.file.refresh') }}
      </button>
    </div>

    <!-- Project view: include graph + project-wide search + cross-file lint (whole config tree) -->
    <details v-if="graph && graph.reachable" class="nb-card bg-surface p-2 text-[11px]">
      <summary class="cursor-pointer font-bold">
        {{ t('configEditor.project.title') }}
        <span v-if="lintActionable" class="ms-1 rounded bg-brand-yellow px-1 text-ink">
          {{ t('configEditor.project.lintBadge', { n: lintActionable }) }}
        </span>
      </summary>

      <div class="mt-2 space-y-3">
        <!-- Project-wide search -->
        <form class="flex flex-wrap items-center gap-1" @submit.prevent="runSearch">
          <input
            v-model="searchQuery"
            type="search"
            :placeholder="t('configEditor.project.searchPlaceholder')"
            class="min-w-[10rem] flex-1 rounded-brutal border border-ink bg-surface px-2 py-1"
          />
          <button type="submit" class="nb-btn bg-surface px-2 py-1" :disabled="searching">
            <span aria-hidden="true">🔎</span> {{ t('configEditor.project.searchBtn') }}
          </button>
        </form>
        <div v-if="searchResult" class="space-y-1">
          <p v-if="!searchResult.matches.length" class="opacity-60">
            {{ t('configEditor.project.noResults') }}
          </p>
          <template v-else>
            <p class="opacity-60">
              {{ t('configEditor.project.matchesCount', { n: searchResult.matches.length }) }}
              <span v-if="searchResult.truncated">· {{ t('configEditor.project.truncated') }}</span>
            </p>
            <ul class="max-h-40 space-y-0.5 overflow-auto font-mono">
              <li v-for="(m, mi) in searchResult.matches" :key="mi">
                <button
                  class="w-full truncate text-start hover:underline"
                  @click="openFile(m.file, true)"
                >
                  <span class="opacity-60">{{ m.file }}:{{ m.line }}</span> · {{ m.text }}
                </button>
              </li>
            </ul>
          </template>
        </div>

        <!-- Include dependency tree -->
        <div v-if="treeRows.length" class="space-y-0.5">
          <p class="font-bold opacity-70">{{ t('configEditor.project.tree') }}</p>
          <ul class="font-mono">
            <li v-for="(row, ri) in treeRows" :key="ri">
              <button
                class="text-start hover:underline"
                :class="row.broken ? 'text-brand-red' : ''"
                :style="{ paddingInlineStart: row.depth * 12 + 'px' }"
                :disabled="row.broken"
                @click="openFile(row.file)"
              >
                <span aria-hidden="true">{{ row.depth ? '↳ ' : '' }}</span
                >{{ row.file
                }}<span v-if="row.broken"> ⚠ {{ t('configEditor.project.missing') }}</span>
              </button>
            </li>
          </ul>
        </div>

        <!-- Cross-file lint -->
        <div v-if="graph.lint.length" class="space-y-1">
          <p class="font-bold opacity-70">{{ t('configEditor.project.lint') }}</p>
          <ul class="space-y-1">
            <li
              v-for="(lt, li) in graph.lint"
              :key="li"
              class="rounded p-1"
              :class="lintClass(lt.level)"
            >
              <button class="w-full text-start hover:underline" @click="openFile(lt.file)">
                <b>{{ ruleLabel(lt.rule) }}</b>
                <span class="font-mono">{{ lt.message }}</span>
                <span class="opacity-60"> — {{ lt.file }}</span>
                <span v-if="lt.files && lt.files.length > 1" class="opacity-60">
                  ({{ lt.files.join(', ') }})
                </span>
              </button>
            </li>
          </ul>
        </div>
      </div>
    </details>

    <!-- File-list states -->
    <p v-if="loadingFiles" class="font-mono text-xs opacity-70">
      {{ t('configEditor.file.loadingList') }}
    </p>
    <p v-else-if="errFiles" class="nb-card bg-brand-red/10 p-2 font-mono text-xs">{{ errFiles }}</p>
    <p v-else-if="!files.length" class="font-mono text-xs opacity-70">
      {{ t('configEditor.file.emptyList') }}
    </p>

    <!-- File-view states -->
    <p v-if="loadingView" class="font-mono text-xs opacity-70">
      {{ t('configEditor.states.loading') }}
    </p>
    <div v-else-if="errView" class="nb-card space-y-2 bg-brand-red/10 p-2">
      <p class="font-mono text-xs">{{ t('configEditor.states.error') }}</p>
      <p class="font-mono text-[11px] opacity-70">{{ errView }}</p>
      <button
        v-if="selected"
        class="nb-btn bg-surface px-2 py-1 text-xs"
        @click="loadView(selected)"
      >
        {{ t('configEditor.states.retry') }}
      </button>
    </div>

    <!-- Parsed view -->
    <template v-if="view && !loadingView && !errView">
      <!-- Summary -->
      <div class="flex flex-wrap items-center gap-2 font-mono text-xs">
        <span class="nb-card bg-surface px-2 py-1">
          {{ t('configEditor.summary.sections', { count: view.section_count }) }}
        </span>
        <span class="nb-card bg-surface px-2 py-1">
          {{ t('configEditor.summary.params', { count: paramTotal }) }}
        </span>
      </div>

      <!-- Validation banner -->
      <div
        class="nb-card p-2"
        :class="
          errorCount ? 'bg-brand-red/10' : warningCount ? 'bg-brand-yellow/20' : 'bg-brand-lime/20'
        "
        role="status"
      >
        <p class="mb-1 text-xs font-bold">{{ t('configEditor.validation.title') }}</p>
        <p v-if="!view.issues.length" class="font-mono text-[11px] opacity-80">
          <span aria-hidden="true">✓</span> {{ t('configEditor.validation.clean') }}
        </p>
        <ul v-else class="space-y-1">
          <li
            v-for="(issue, i) in view.issues"
            :key="i"
            class="flex items-start gap-1.5 font-mono text-[11px]"
          >
            <span
              class="shrink-0 rounded px-1 font-bold"
              :class="
                issue.level === 'error' ? 'bg-brand-red text-paper' : 'bg-brand-yellow text-ink'
              "
            >
              {{
                issue.level === 'error'
                  ? t('configEditor.validation.error')
                  : t('configEditor.validation.warning')
              }}
            </span>
            <span class="min-w-0">{{ issue.message }}</span>
          </li>
        </ul>
      </div>

      <!-- Driver value sanity: run_current vs the driver ceiling / mapped-motor rating + microsteps -->
      <div
        v-if="sanity && sanity.reachable && sanity.findings.length"
        class="nb-card space-y-1 bg-brand-yellow/15 p-2"
      >
        <p class="text-xs font-bold">
          {{ t('configEditor.sanity.title', { n: sanity.findings.length }) }}
        </p>
        <ul class="space-y-1 text-[11px]">
          <li v-for="(f, i) in sanity.findings" :key="i" class="flex flex-wrap items-start gap-1">
            <span
              class="shrink-0 rounded px-1 font-bold"
              :class="f.level === 'error' ? 'bg-brand-red text-paper' : 'bg-brand-yellow text-ink'"
            >
              {{ f.level === 'error' ? '✕' : '⚠' }}
            </span>
            <span class="min-w-0 font-mono">{{ sanityMsg(f) }}</span>
          </li>
        </ul>
        <p class="text-[10px] opacity-50">
          {{ t('configEditor.sanity.note', { n: sanity.checked }) }}
        </p>
      </div>

      <!-- Pin Doctor: whole-config pin-conflict + electronics-caveat scan -->
      <div
        v-if="pinDoctor && pinDoctor.reachable && pinDoctor.total > 0"
        class="nb-card space-y-2 bg-brand-red/10 p-2"
      >
        <p class="text-xs font-bold">
          {{ t('configEditor.pinDoctor.title', { n: pinDoctor.total }) }}
        </p>
        <div v-for="m in pinDoctor.mcus" :key="m.name" class="space-y-1">
          <p class="font-mono text-[11px] opacity-70">
            {{ m.name }}<span v-if="m.board_name"> · {{ m.board_name }}</span>
          </p>
          <ul class="space-y-0.5">
            <li
              v-for="(f, i) in m.findings"
              :key="i"
              class="flex flex-wrap items-start gap-1 font-mono text-[10px]"
            >
              <span
                class="shrink-0 rounded px-1 font-bold"
                :class="
                  f.kind === 'double_assign'
                    ? 'bg-brand-red text-paper'
                    : 'bg-brand-yellow text-ink'
                "
              >
                {{
                  f.kind === 'double_assign'
                    ? t('configEditor.pinDoctor.conflict')
                    : t('configEditor.pinDoctor.caveat')
                }}
              </span>
              <b>{{ f.pin }}</b>
              <span class="min-w-0">{{ f.message }}</span>
            </li>
          </ul>
        </div>
      </div>

      <!-- Disk vs live: what Klipper is actually running (drift + pending SAVE_CONFIG + warnings) -->
      <div v-if="hasLiveInfo && drift" class="nb-card space-y-2 bg-brand-yellow/15 p-2">
        <p class="text-xs font-bold">{{ t('configEditor.drift.title') }}</p>
        <p v-if="drift.save_config_pending" class="font-mono text-[11px]">
          <span aria-hidden="true">⚠</span> {{ t('configEditor.drift.pending') }}
        </p>
        <div v-if="drift.warnings.length" class="space-y-0.5">
          <p class="text-[11px] font-bold opacity-70">
            {{ t('configEditor.drift.warningsTitle') }}
          </p>
          <ul class="space-y-0.5 font-mono text-[10px] opacity-80">
            <li v-for="(w, i) in drift.warnings" :key="i">{{ w }}</li>
          </ul>
        </div>
        <div v-if="drift.drifts.length" class="space-y-1">
          <p class="text-[11px]">{{ t('configEditor.drift.count', { n: drift.drifts.length }) }}</p>
          <ul class="space-y-1">
            <li
              v-for="(d, i) in drift.drifts"
              :key="i"
              class="flex flex-wrap items-center gap-1.5 font-mono text-[10px]"
            >
              <span class="opacity-60">[{{ d.section }}]</span>
              <b>{{ d.key }}</b>
              <span class="rounded bg-brand-red/20 px-1">{{ d.disk }}</span>
              <span aria-hidden="true">→</span>
              <span class="rounded bg-brand-lime/30 px-1">{{ d.live }}</span>
              <button
                class="nb-btn bg-surface px-1 py-0 disabled:opacity-50"
                :disabled="adopting === d.section + '|' + d.key"
                @click="adoptLive(d)"
              >
                {{ t('configEditor.drift.adopt') }}
              </button>
            </li>
          </ul>
        </div>
      </div>

      <!-- Backup timeline: snapshots from past saves, with diff-vs-current and gated restore -->
      <details
        v-if="backups && backups.reachable && backups.backups.length"
        class="nb-card bg-surface p-2 text-[11px]"
      >
        <summary class="cursor-pointer text-xs font-bold">
          {{ t('configEditor.backups.title', { n: backups.backups.length }) }}
        </summary>
        <ul class="mt-2 space-y-1">
          <li v-for="b in backups.backups" :key="b.path" class="nb-card bg-paper/40 p-1.5">
            <div class="flex flex-wrap items-center gap-2">
              <span class="font-mono">{{ b.when }}</span>
              <span v-if="b.size != null" class="opacity-50">{{ b.size }} B</span>
              <span class="flex-1"></span>
              <button
                class="nb-btn bg-surface px-2 py-0.5 text-[10px]"
                :disabled="backupBusy === b.path"
                @click="toggleDiff(b)"
              >
                {{
                  diffPath === b.path
                    ? t('configEditor.backups.hideDiff')
                    : t('configEditor.backups.diff')
                }}
              </button>
              <button
                class="nb-btn bg-brand-yellow px-2 py-0.5 text-[10px]"
                :disabled="backupBusy === b.path"
                @click="restoreBackup(b)"
              >
                {{ t('configEditor.backups.restore') }}
              </button>
            </div>
            <div v-if="diffPath === b.path" class="mt-1.5 space-y-1">
              <p class="opacity-70">
                <span class="text-brand-red">−{{ diffSummary?.removed ?? 0 }}</span>
                /
                <span class="text-brand-lime">+{{ diffSummary?.added ?? 0 }}</span>
                · {{ t('configEditor.backups.diffHint') }}
              </p>
              <pre
                class="max-h-60 overflow-auto rounded bg-ink/5 p-1 font-mono text-[10px] leading-snug"
              ><template v-for="(r, ri) in diffRows" :key="ri"><div v-if="r.hidden" class="opacity-40">{{ t('configEditor.backups.unchanged', { n: r.hidden }) }}</div><div v-else :class="r.kind === 'del' ? 'text-brand-red' : r.kind === 'add' ? 'text-brand-lime' : 'opacity-60'">{{ r.kind === 'del' ? '− ' : r.kind === 'add' ? '+ ' : '  ' }}{{ r.text }}</div></template></pre>
            </div>
          </li>
        </ul>
        <p class="mt-1 text-[10px] opacity-50">{{ t('configEditor.backups.note') }}</p>
      </details>

      <!-- Insert a hardware-accurate config block from the catalog -->
      <details class="nb-card bg-surface p-2 text-[11px]">
        <summary class="cursor-pointer text-xs font-bold">
          {{ t('configEditor.catalog.title') }}
        </summary>
        <div class="mt-2 space-y-2">
          <p class="opacity-70">{{ t('configEditor.catalog.hint') }}</p>
          <WidgetTabs v-model="catalogType" :tabs="CATALOG_TABS" />
          <HardwarePicker
            :key="catalogType"
            :type="catalogType"
            :model-value="catalogPick"
            :placeholder="t('configEditor.catalog.pickPlaceholder')"
            :disabled="inserting"
            @update:model-value="onCatalogPick"
          />
          <p
            v-if="insertMsg"
            class="font-mono text-[11px]"
            :class="insertErr ? 'text-brand-red' : 'text-ink'"
          >
            <span aria-hidden="true">{{ insertErr ? '⚠' : '✓' }}</span> {{ insertMsg }}
          </p>
        </div>
      </details>

      <!-- View toggle -->
      <WidgetTabs v-model="viewMode" :tabs="VIEW_TABS" />

      <!-- Structured: collapsible sections -->
      <template v-if="viewMode === 'structured'">
        <div class="flex items-center justify-between gap-2">
          <p v-if="dirty" class="font-mono text-[11px] text-brand-red">
            <span aria-hidden="true">●</span> {{ t('configEditor.save.unsaved') }} —
            <button class="underline" @click="viewMode = 'raw'">
              {{ t('configEditor.tmc.review') }}
            </button>
          </p>
          <span v-else></span>
          <div class="flex gap-2">
            <button class="nb-btn bg-surface px-2 py-0.5 text-[11px]" @click="expandAll">
              {{ t('configEditor.view.expandAll') }}
            </button>
            <button class="nb-btn bg-surface px-2 py-0.5 text-[11px]" @click="collapseAll">
              {{ t('configEditor.view.collapseAll') }}
            </button>
          </div>
        </div>

        <ul class="space-y-2">
          <li
            v-for="(section, i) in view.sections"
            :key="i"
            class="nb-card overflow-hidden bg-surface"
          >
            <button
              class="flex w-full items-center justify-between gap-2 px-2 py-1.5 text-start"
              :aria-expanded="!!open[i]"
              @click="toggleSection(i, section.type)"
            >
              <span class="min-w-0 truncate font-mono text-xs">
                <span aria-hidden="true">{{ open[i] ? '▾' : '▸' }}</span>
                <b>[{{ section.header }}]</b>
                <span
                  v-if="section.is_save_config"
                  class="ms-1 rounded bg-ink px-1 text-[10px] text-paper"
                >
                  {{ t('configEditor.section.saveBadge') }}
                </span>
              </span>
              <span class="shrink-0 font-mono text-[10px] opacity-60">
                {{ t('configEditor.section.paramsCount', { count: section.params.length }) }}
              </span>
            </button>

            <div v-if="open[i]" class="border-t-2 border-ink/20 px-2 py-1.5">
              <!-- Inline knowledge: what this section does + a deep-link to its catalog entity -->
              <div
                v-if="sectionBlurb(section.type) || tmcModel(section.type)"
                class="mb-1.5 space-y-1"
              >
                <p v-if="sectionBlurb(section.type)" class="text-[11px] italic opacity-70">
                  {{ sectionBlurb(section.type) }}
                </p>
                <button
                  v-if="tmcModel(section.type)"
                  class="nb-btn bg-brand-cyan px-2 py-0.5 text-[10px]"
                  @click="openDriverInBrowser(tmcModel(section.type)!)"
                >
                  {{
                    t('configEditor.knowledge.viewDriver', {
                      model: tmcModel(section.type)!.toUpperCase(),
                    })
                  }}
                </button>
              </div>
              <p v-if="!section.params.length" class="font-mono text-[11px] opacity-60">
                {{ t('configEditor.section.noParams') }}
              </p>
              <table v-else class="w-full border-collapse font-mono text-[11px]">
                <thead>
                  <tr class="text-start opacity-60">
                    <th class="py-0.5 pe-2 text-start font-bold">
                      {{ t('configEditor.section.paramHead') }}
                    </th>
                    <th class="py-0.5 text-start font-bold">
                      {{ t('configEditor.section.valueHead') }}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(p, pi) in section.params" :key="pi" class="align-top">
                    <td class="py-0.5 pe-2 font-bold">{{ p.key }}</td>
                    <td class="whitespace-pre-wrap break-words py-0.5">
                      <!-- Typed control for a TMC register field the policy knows -->
                      <template v-if="policyFor(section.type, p.key) as FieldPolicyEntry | null">
                        <span class="inline-flex flex-wrap items-center gap-1">
                          <input
                            v-if="policyFor(section.type, p.key)!.control === 'toggle'"
                            type="checkbox"
                            :checked="p.value === '1' || p.value.toLowerCase() === 'true'"
                            @change="
                              onTmcEdit(
                                section,
                                p,
                                ($event.target as HTMLInputElement).checked ? '1' : '0',
                              )
                            "
                          />
                          <select
                            v-else-if="policyFor(section.type, p.key)!.enum"
                            :value="p.value"
                            class="rounded-brutal border border-ink bg-surface px-1 py-0.5"
                            @change="
                              onTmcEdit(section, p, ($event.target as HTMLSelectElement).value)
                            "
                          >
                            <option v-for="o in policyFor(section.type, p.key)!.enum" :key="o">
                              {{ o }}
                            </option>
                          </select>
                          <input
                            v-else
                            type="number"
                            :value="p.value"
                            :min="policyFor(section.type, p.key)!.min"
                            :max="policyFor(section.type, p.key)!.max"
                            class="w-20 rounded-brutal border border-ink bg-surface px-1 py-0.5"
                            @change="
                              onTmcEdit(
                                section,
                                p,
                                clampNum(
                                  policyFor(section.type, p.key)!,
                                  ($event.target as HTMLInputElement).value,
                                ),
                              )
                            "
                          />
                          <span class="text-[10px] opacity-50">{{
                            rangeHint(policyFor(section.type, p.key)!)
                          }}</span>
                        </span>
                      </template>
                      <!-- Pin-aware control for a `*_pin` param whose MCU resolves to a board -->
                      <template v-else-if="isPinParam(p) && mcuForPin(p.value)">
                        <span class="inline-flex flex-wrap items-center gap-1">
                          <input
                            :value="p.value"
                            :list="`pins-${i}-${pi}`"
                            class="w-32 rounded-brutal border border-ink bg-surface px-1 py-0.5"
                            :aria-label="p.key"
                            @change="
                              onTmcEdit(section, p, ($event.target as HTMLInputElement).value)
                            "
                          />
                          <datalist :id="`pins-${i}-${pi}`">
                            <option v-for="o in pinOptions(p.value)" :key="o" :value="o" />
                          </datalist>
                          <span
                            v-if="pinFlags(p.value).offBoard"
                            class="rounded bg-ink/10 px-1 text-[10px] opacity-70"
                            :title="t('configEditor.pinEdit.offBoardHint')"
                          >
                            {{ t('configEditor.pinEdit.offBoard') }}
                          </span>
                          <span
                            v-if="pinFlags(p.value).doubleAssign"
                            class="rounded bg-brand-yellow px-1 text-[10px] font-bold text-ink"
                            :title="t('configEditor.pinEdit.doubleHint')"
                          >
                            {{ t('configEditor.pinEdit.double') }}
                          </span>
                          <span
                            v-if="pinFlags(p.value).caveat"
                            class="rounded bg-brand-yellow px-1 text-[10px] font-bold text-ink"
                            :title="pinFlags(p.value).caveat || ''"
                          >
                            {{ t('configEditor.pinEdit.caveat') }}
                          </span>
                          <span v-if="p.comment" class="opacity-50">{{ p.comment }}</span>
                        </span>
                      </template>
                      <template v-else>
                        {{ p.value || '—'
                        }}<span v-if="p.comment" class="opacity-50"> {{ p.comment }}</span>
                      </template>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </li>
        </ul>
      </template>

      <!-- Raw (editable) -->
      <template v-else>
        <p class="text-[11px] opacity-70">{{ t('configEditor.edit.hint') }}</p>
        <textarea
          v-model="draft"
          spellcheck="false"
          class="nb-card h-[28rem] w-full resize-y overflow-auto bg-surface p-2 font-mono text-[11px] leading-snug"
          :aria-label="t('configEditor.view.raw')"
        ></textarea>

        <!-- Save toolbar -->
        <div class="flex flex-wrap items-center gap-2">
          <button
            class="nb-btn bg-brand-cyan px-3 py-1 text-xs"
            :disabled="!dirty || saving"
            @click="openSaveConfirm"
          >
            {{ saving ? t('configEditor.save.saving') : t('configEditor.save.button') }}
          </button>
          <button
            v-if="dirty"
            class="nb-btn bg-surface px-2 py-1 text-xs"
            :disabled="saving"
            @click="revert"
          >
            {{ t('configEditor.save.revert') }}
          </button>
          <span v-if="dirty" class="font-mono text-[11px] text-brand-red">
            <span aria-hidden="true">●</span> {{ t('configEditor.save.unsaved') }}
          </span>
        </div>

        <!-- Save confirm gate -->
        <div
          v-if="confirmMode === 'save'"
          class="nb-card space-y-2 border-brand-red bg-brand-red/10 p-2"
        >
          <p class="text-xs font-bold">{{ t('configEditor.save.confirmTitle') }}</p>
          <p class="text-[11px] opacity-80">
            {{ t('configEditor.save.confirmBody', { file: selected ?? '' }) }}
          </p>
          <label class="flex items-center gap-2 text-[11px]">
            <input v-model="ack" type="checkbox" />
            {{ t('configEditor.save.ack') }}
          </label>
          <div class="flex gap-2">
            <button
              class="nb-btn bg-brand-red px-3 py-1 text-xs text-paper"
              :disabled="!ack || saving"
              @click="doSave"
            >
              {{ t('configEditor.save.confirm') }}
            </button>
            <button class="nb-btn bg-surface px-2 py-1 text-xs" @click="cancelConfirm">
              {{ t('configEditor.save.cancel') }}
            </button>
          </div>
        </div>

        <!-- Save error -->
        <p v-if="saveErr" class="nb-card bg-brand-red/10 p-2 font-mono text-[11px]">
          {{ saveErr }}
        </p>

        <!-- Saved + restart prompt -->
        <div v-if="saveMsg" class="nb-card space-y-2 bg-brand-lime/20 p-2">
          <p class="font-mono text-[11px]"><span aria-hidden="true">✓</span> {{ saveMsg }}</p>
          <template v-if="showRestartPrompt">
            <p class="text-[11px]">{{ t('configEditor.restart.prompt') }}</p>
            <button
              class="nb-btn bg-brand-yellow px-3 py-1 text-xs text-ink"
              :disabled="restarting"
              @click="openRestartConfirm"
            >
              {{
                restarting ? t('configEditor.restart.restarting') : t('configEditor.restart.button')
              }}
            </button>
          </template>
        </div>

        <!-- Restart confirm gate -->
        <div
          v-if="confirmMode === 'restart'"
          class="nb-card space-y-2 border-brand-red bg-brand-yellow/20 p-2"
        >
          <p class="text-xs font-bold">{{ t('configEditor.restart.confirmTitle') }}</p>
          <p class="text-[11px] opacity-80">{{ t('configEditor.restart.confirmBody') }}</p>
          <div class="flex gap-2">
            <button
              class="nb-btn bg-brand-red px-3 py-1 text-xs text-paper"
              :disabled="restarting"
              @click="doRestart"
            >
              {{ t('configEditor.restart.confirm') }}
            </button>
            <button class="nb-btn bg-surface px-2 py-1 text-xs" @click="cancelConfirm">
              {{ t('configEditor.restart.cancel') }}
            </button>
          </div>
        </div>

        <!-- Restart result -->
        <p v-if="restartMsg" class="nb-card bg-brand-lime/20 p-2 font-mono text-[11px]">
          <span aria-hidden="true">✓</span> {{ restartMsg }}
        </p>
        <p v-if="restartErr" class="nb-card bg-brand-red/10 p-2 font-mono text-[11px]">
          {{ restartErr }}
        </p>
      </template>
    </template>
  </div>
</template>
