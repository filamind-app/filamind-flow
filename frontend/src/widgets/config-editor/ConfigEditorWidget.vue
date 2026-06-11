<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import ComboSelect from '@/components/ui/ComboSelect.vue'
import HelpDrawer from '@/components/ui/HelpDrawer.vue'
import WidgetTabs from '@/components/ui/WidgetTabs.vue'
import { describeError } from '@/core/describeError'
import {
  fetchBoardDetail,
  fetchDriverDetail,
  fetchMotorDetail,
} from '@/widgets/hardware-browser/api'
import HardwarePicker from '@/widgets/hardware-browser/HardwarePicker.vue'

import {
  adoptParam,
  ApiError,
  fetchConfigDrift,
  fetchConfigFile,
  fetchConfigFiles,
  fetchPinDoctor,
  restartFirmware,
  saveConfigFile,
} from './api'
import HelpIllo from './HelpIllo.vue'
import { GLOSSARY_KEYS, HELP_ILLO, HELP_TOPICS } from './help'
import type {
  ConfigDrift,
  ConfigDriftResult,
  ConfigFileInfo,
  ConfigFileView,
  PinDoctorResult,
} from './types'

const { t } = useI18n({ useScope: 'global' })

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
  } catch (e) {
    errView.value = describeError(e)
    view.value = null
    draft.value = ''
  } finally {
    loadingView.value = false
  }
}

function expandAll(): void {
  const next: Record<number, boolean> = {}
  ;(view.value?.sections ?? []).forEach((_, i) => (next[i] = true))
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
        <div class="flex justify-end gap-2">
          <button class="nb-btn bg-surface px-2 py-0.5 text-[11px]" @click="expandAll">
            {{ t('configEditor.view.expandAll') }}
          </button>
          <button class="nb-btn bg-surface px-2 py-0.5 text-[11px]" @click="collapseAll">
            {{ t('configEditor.view.collapseAll') }}
          </button>
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
              @click="open[i] = !open[i]"
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
                      {{ p.value || '—'
                      }}<span v-if="p.comment" class="opacity-50"> {{ p.comment }}</span>
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
