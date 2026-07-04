<script setup lang="ts">
/** Host Control · Boot parameters - edit the host's boot configuration (device-tree overlays +
 *  kernel args) through curated capability cards plus a raw Advanced editor. Every edit is STAGED,
 *  previewed as a unified diff, backed up before writing, and applied only on an explicit Apply.
 *  Changes need a reboot to take effect; nothing reboots automatically. Gated-write pattern mirrors
 *  SystemPanel. */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { describeError } from '@/core/describeError'

import {
  applyBootChange,
  fetchBootParams,
  HostActionError,
  previewBootChange,
  rebootForBoot,
  revertBootFile,
} from './api'
import { BOOT_CATALOG, type BootItem, fileFor, opsForValue, readValue } from './bootCatalog'
import type { BootFile, BootOp, BootParamsState, BootPreview, SystemActionResult } from './types'

const { t, te } = useI18n({ useScope: 'global' })

const state = ref<BootParamsState | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)

const busy = ref<string | null>(null)
const note = ref<string | null>(null)
const actErr = ref<string | null>(null)
const rebootInfo = ref<string | null>(null)

/** Staged curated edits: item.key -> new display value (only while it differs from the file). */
const pending = ref<Record<string, string>>({})
/** Staged raw Advanced ops (add/remove overlay / dtparam), applied after the curated ops. */
const advOps = ref<BootOp[]>([])
const advOverlay = ref('')
const advParamKey = ref('')
const advParamValue = ref('')
const showAdvanced = ref(false)

const preview = ref<BootPreview | null>(null)
const warnAck = ref(false)
const confirmRevert = ref(false)
const rebootText = ref('')

async function reload(): Promise<void> {
  if (!state.value) loading.value = true
  error.value = null
  try {
    state.value = await fetchBootParams()
    resetStaged()
  } catch (e) {
    error.value = describeError(e)
  } finally {
    loading.value = false
  }
}

function resetStaged(): void {
  pending.value = {}
  advOps.value = []
  advOverlay.value = ''
  advParamKey.value = ''
  advParamValue.value = ''
  preview.value = null
  warnAck.value = false
  confirmRevert.value = false
  rebootText.value = ''
}

onMounted(reload)

// -- catalog rendering ----------------------------------------------------------
const groups = computed(() => (state.value ? BOOT_CATALOG[state.value.platform] : []))
/** The primary boot file the curated cards + Advanced edit (armbianEnv.txt / config.txt). */
const primary = computed<BootFile | undefined>(() => state.value?.files[0])

function itemLabel(item: BootItem): string {
  return t(`hostControl.boot.params.items.${item.key}.label`)
}
function itemPurpose(item: BootItem): string {
  return t(`hostControl.boot.params.items.${item.key}.purpose`)
}
function itemCaveat(item: BootItem): string {
  const key = `hostControl.boot.params.items.${item.key}.caveat`
  return te(key) ? t(key) : ''
}
function optLabel(value: string): string {
  const key = `hostControl.boot.params.opt.${value}`
  return te(key) ? t(key) : value
}

/** The current effective value for an item (staged if edited, else read from the file). */
function valueOf(item: BootItem): string {
  if (item.key in pending.value) return pending.value[item.key]
  return readValue(fileFor(state.value?.files ?? [], item), item)
}
function baseValue(item: BootItem): string {
  return readValue(fileFor(state.value?.files ?? [], item), item)
}
function isChanged(item: BootItem): boolean {
  return item.key in pending.value && pending.value[item.key] !== baseValue(item)
}

/** Stage a new value for an item (drops it from `pending` when back to the file value). */
function stage(item: BootItem, next: string): void {
  preview.value = null // any edit invalidates a prior preview
  warnAck.value = false
  if (next === baseValue(item)) {
    delete pending.value[item.key]
  } else {
    pending.value[item.key] = next
  }
}

function onToggle(item: BootItem, e: Event): void {
  stage(item, (e.target as HTMLInputElement).checked ? 'on' : 'off')
}

// -- Advanced (raw overlay / dtparam ops) ---------------------------------------
const advOverlays = computed<string[]>(() => {
  const f = primary.value
  if (!f) return []
  if (f.format === 'armbian') return (f.overlays as string[]) || []
  return ((f.overlays as { name: string }[]) || []).map((o) => o.name)
})

function stageAdvOp(op: BootOp): void {
  advOps.value.push(op)
  preview.value = null
  warnAck.value = false
}
function addAdvOverlay(): void {
  const name = advOverlay.value.trim()
  if (!name) return
  const op = primary.value?.format === 'armbian' ? 'add_overlay' : 'add_dtoverlay'
  stageAdvOp({ op, name })
  advOverlay.value = ''
}
function removeAdvOverlay(name: string): void {
  const op = primary.value?.format === 'armbian' ? 'remove_overlay' : 'remove_dtoverlay'
  stageAdvOp({ op, name })
}
function addAdvParam(): void {
  const key = advParamKey.value.trim()
  if (!key) return
  stageAdvOp({ op: 'set_dtparam', key, value: advParamValue.value.trim() })
  advParamKey.value = ''
  advParamValue.value = ''
}
function clearAdvanced(): void {
  advOps.value = []
  preview.value = null
}

// -- staged ops / preview / apply -----------------------------------------------
const stagedOps = computed<BootOp[]>(() => {
  const ops: BootOp[] = []
  for (const g of groups.value) {
    for (const item of g.items) {
      if (isChanged(item)) ops.push(...opsForValue(item, baseValue(item), pending.value[item.key]))
    }
  }
  return [...ops, ...advOps.value]
})
const hasStaged = computed(() => stagedOps.value.length > 0)
const primaryName = computed(() => primary.value?.name ?? '')

async function runPreview(): Promise<void> {
  if (!hasStaged.value) return
  busy.value = 'preview'
  clearMessages()
  try {
    preview.value = await previewBootChange(primaryName.value, stagedOps.value)
    warnAck.value = false
  } catch (e) {
    actErr.value = e instanceof HostActionError ? e.message : describeError(e)
  } finally {
    busy.value = null
  }
}

const canApply = computed(() => {
  const p = preview.value
  if (!p || !p.diff.length) return false
  if (p.validation.errors.length) return false
  if (p.validation.warnings.length && !warnAck.value) return false
  return true
})

async function runApply(): Promise<void> {
  if (!canApply.value || !preview.value) return
  busy.value = 'apply'
  clearMessages()
  try {
    const r = await applyBootChange(primaryName.value, stagedOps.value, preview.value.before_hash)
    showResult(r, t('hostControl.boot.params.apply.done'))
    await reload()
  } catch (e) {
    actErr.value = e instanceof HostActionError ? e.message : describeError(e)
  } finally {
    busy.value = null
  }
}

async function runRevert(): Promise<void> {
  confirmRevert.value = false
  busy.value = 'revert'
  clearMessages()
  try {
    showResult(await revertBootFile(primaryName.value), t('hostControl.boot.params.revert.done'))
    await reload()
  } catch (e) {
    actErr.value = e instanceof HostActionError ? e.message : describeError(e)
  } finally {
    busy.value = null
  }
}

const rebootReady = computed(
  () => rebootText.value.trim() === t('hostControl.boot.params.reboot.token'),
)

async function runReboot(): Promise<void> {
  if (!rebootReady.value) return
  busy.value = 'reboot'
  clearMessages()
  try {
    const r = await rebootForBoot()
    if (r.ok) {
      // the host is going down - the socket will drop; don't reload over a dying link
      rebootInfo.value = t('hostControl.boot.params.reboot.rebooting')
    } else {
      actErr.value = r.needs_setup ? t('hostControl.boot.params.needsSetup') : r.output
    }
  } catch (e) {
    actErr.value = e instanceof HostActionError ? e.message : describeError(e)
  } finally {
    busy.value = null
  }
}

const hasBackup = computed(() => (primary.value?.backups.length ?? 0) > 0)

function showResult(r: SystemActionResult, okMsg: string): void {
  if (r.ok) note.value = r.output || okMsg
  else actErr.value = r.needs_setup ? t('hostControl.boot.params.needsSetup') : r.output
}
function clearMessages(): void {
  note.value = null
  actErr.value = null
  rebootInfo.value = null
}

function diffClass(line: string): string {
  if (line.startsWith('+') && !line.startsWith('+++')) return 'text-brand-green'
  if (line.startsWith('-') && !line.startsWith('---')) return 'text-brand-red'
  if (line.startsWith('@@')) return 'opacity-50'
  return 'opacity-70'
}
</script>

<template>
  <div class="space-y-3">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <p class="min-w-0 flex-1 text-[11px] opacity-70">{{ t('hostControl.boot.params.intro') }}</p>
      <button type="button" class="nb-btn text-xs" :disabled="loading || !!busy" @click="reload">
        ↻ {{ t('hostControl.boot.params.refresh') }}
      </button>
    </div>

    <p v-if="loading" class="font-mono text-xs opacity-70">
      {{ t('hostControl.boot.params.loading') }}
    </p>
    <p v-else-if="error" role="alert" class="nb-card bg-brand-red/10 p-2 font-mono text-xs">
      {{ error }}
    </p>

    <template v-else-if="state">
      <!-- result / error bars -->
      <p v-if="note" class="nb-card bg-brand-green/10 p-2 font-mono text-[11px] text-brand-green">
        ✓ {{ note }}
      </p>
      <p
        v-if="rebootInfo"
        role="status"
        class="nb-card bg-brand-yellow/15 p-2 font-mono text-[11px]"
      >
        ⟳ {{ rebootInfo }}
      </p>
      <p v-if="actErr" role="alert" class="nb-card bg-brand-red/10 p-2 font-mono text-[11px]">
        {{ actErr }}
      </p>

      <!-- platform + read-only -->
      <p class="font-mono text-[11px] opacity-60">
        {{ t('hostControl.boot.params.platform.' + state.platform) }}
      </p>
      <p v-if="!state.editable" class="nb-card bg-brand-yellow/15 p-2 text-[11px]" role="status">
        {{ t('hostControl.boot.params.platform.unknown') }}
      </p>

      <!-- reboot-required banner -->
      <div
        v-if="state.editable && state.reboot_required"
        class="nb-card space-y-1.5 bg-brand-yellow/15 p-2"
        role="status"
      >
        <p class="text-[11px] font-bold">⟳ {{ t('hostControl.boot.params.reboot.banner') }}</p>
        <p class="text-[11px]">{{ t('hostControl.boot.params.reboot.prompt') }}</p>
        <div class="flex flex-wrap items-center gap-2">
          <input
            v-model="rebootText"
            type="text"
            :placeholder="t('hostControl.boot.params.reboot.token')"
            class="w-32 rounded-brutal border-2 border-ink bg-paper px-2 py-1 font-mono text-[11px]"
          />
          <button
            type="button"
            class="nb-btn border-brand-red text-[11px] text-brand-red"
            :disabled="busy === 'reboot' || !rebootReady"
            @click="runReboot"
          >
            ⟳ {{ t('hostControl.boot.params.reboot.button') }}
          </button>
        </div>
      </div>

      <template v-if="state.editable">
        <!-- curated capability groups -->
        <section v-for="g in groups" :key="g.id" class="nb-card space-y-2 bg-surface p-3">
          <h3 class="text-xs font-bold uppercase tracking-wide opacity-60">
            {{ t('hostControl.boot.params.groups.' + g.id) }}
          </h3>
          <div
            v-for="item in g.items"
            :key="item.key"
            class="space-y-1 border-t border-ink/10 pt-2 first:border-0 first:pt-0"
          >
            <div class="flex items-start justify-between gap-2">
              <div class="min-w-0 flex-1">
                <p class="text-xs font-bold">
                  {{ itemLabel(item) }}
                  <span v-if="isChanged(item)" class="nb-badge ms-1 bg-brand-cyan text-[9px]">
                    {{ t('hostControl.boot.params.control.changed') }}
                  </span>
                </p>
                <p class="text-[11px] opacity-60">{{ itemPurpose(item) }}</p>
              </div>
              <!-- toggle -->
              <label
                v-if="item.control === 'toggle'"
                class="flex shrink-0 cursor-pointer items-center"
              >
                <input
                  type="checkbox"
                  class="h-4 w-4 accent-ink"
                  :checked="valueOf(item) === 'on'"
                  @change="onToggle(item, $event)"
                />
              </label>
              <!-- select -->
              <select
                v-else-if="item.control === 'select'"
                class="shrink-0 rounded-brutal border-2 border-ink bg-paper px-2 py-1 font-mono text-[11px]"
                :value="valueOf(item)"
                @change="stage(item, ($event.target as HTMLSelectElement).value)"
              >
                <option value="">{{ t('hostControl.boot.params.control.disabled') }}</option>
                <option v-for="o in item.variants ?? item.options" :key="o" :value="o">
                  {{ optLabel(o) }}
                </option>
              </select>
              <!-- number -->
              <input
                v-else-if="item.control === 'number'"
                type="number"
                :min="item.min"
                :max="item.max"
                :value="valueOf(item)"
                class="w-20 shrink-0 rounded-brutal border-2 border-ink bg-paper px-2 py-1 font-mono text-[11px]"
                @change="stage(item, ($event.target as HTMLInputElement).value)"
              />
            </div>
            <p v-if="itemCaveat(item)" class="text-[11px] text-brand-red/80">
              ⚠ {{ itemCaveat(item) }}
            </p>
          </div>
        </section>

        <!-- Advanced -->
        <section class="nb-card space-y-2 bg-surface p-3">
          <button
            type="button"
            class="flex w-full items-center justify-between text-xs font-bold uppercase tracking-wide opacity-60"
            @click="showAdvanced = !showAdvanced"
          >
            <span>{{ t('hostControl.boot.params.advanced.title') }}</span>
            <span>{{ showAdvanced ? '▾' : '▸' }}</span>
          </button>
          <template v-if="showAdvanced">
            <p class="text-[11px] text-brand-red">
              ⚠ {{ t('hostControl.boot.params.advanced.warn') }}
            </p>
            <!-- overlays -->
            <p class="text-[11px] font-bold opacity-70">
              {{ t('hostControl.boot.params.advanced.overlays') }}
            </p>
            <div class="flex flex-wrap gap-1">
              <span
                v-for="ov in advOverlays"
                :key="ov"
                class="inline-flex items-center gap-1 rounded-brutal border-2 border-ink bg-paper px-1.5 py-0.5 font-mono text-[11px]"
              >
                {{ ov }}
                <button
                  type="button"
                  class="text-brand-red"
                  :aria-label="t('hostControl.boot.params.advanced.remove')"
                  @click="removeAdvOverlay(ov)"
                >
                  ✕
                </button>
              </span>
              <span v-if="!advOverlays.length" class="text-[11px] opacity-50">—</span>
            </div>
            <div class="flex flex-wrap items-end gap-2">
              <input
                v-model="advOverlay"
                type="text"
                :placeholder="t('hostControl.boot.params.advanced.overlayName')"
                class="min-w-0 flex-1 rounded-brutal border-2 border-ink bg-paper px-2 py-1 font-mono text-[11px]"
                @keyup.enter="addAdvOverlay"
              />
              <button
                type="button"
                class="nb-btn text-[11px]"
                :disabled="!advOverlay.trim()"
                @click="addAdvOverlay"
              >
                + {{ t('hostControl.boot.params.advanced.addOverlay') }}
              </button>
            </div>
            <!-- dtparams (rpi only) -->
            <template v-if="primary?.format === 'config.txt'">
              <p class="text-[11px] font-bold opacity-70">
                {{ t('hostControl.boot.params.advanced.dtparams') }}
              </p>
              <div class="flex flex-wrap items-end gap-2">
                <input
                  v-model="advParamKey"
                  type="text"
                  :placeholder="t('hostControl.boot.params.advanced.paramKey')"
                  class="w-28 rounded-brutal border-2 border-ink bg-paper px-2 py-1 font-mono text-[11px]"
                />
                <input
                  v-model="advParamValue"
                  type="text"
                  :placeholder="t('hostControl.boot.params.advanced.paramValue')"
                  class="w-20 rounded-brutal border-2 border-ink bg-paper px-2 py-1 font-mono text-[11px]"
                />
                <button
                  type="button"
                  class="nb-btn text-[11px]"
                  :disabled="!advParamKey.trim()"
                  @click="addAdvParam"
                >
                  + {{ t('hostControl.boot.params.advanced.addParam') }}
                </button>
              </div>
            </template>
            <div v-if="advOps.length" class="flex items-center justify-between gap-2 text-[11px]">
              <span class="opacity-70">{{
                t('hostControl.boot.params.advanced.staged', { n: advOps.length })
              }}</span>
              <button type="button" class="nb-btn text-[11px]" @click="clearAdvanced">
                {{ t('hostControl.boot.params.advanced.clear') }}
              </button>
            </div>
          </template>
        </section>

        <!-- Preview / Apply bar -->
        <section class="nb-card space-y-2 bg-surface p-3">
          <div class="flex flex-wrap items-center gap-2">
            <button
              type="button"
              class="nb-btn text-xs"
              :disabled="!hasStaged || busy === 'preview'"
              @click="runPreview"
            >
              {{ t('hostControl.boot.params.preview.button') }}
            </button>
            <span v-if="!hasStaged" class="text-[11px] opacity-50">
              {{ t('hostControl.boot.params.preview.none') }}
            </span>
            <button
              v-if="hasBackup"
              type="button"
              class="nb-btn ms-auto border-brand-red text-[11px] text-brand-red"
              :disabled="!!busy"
              @click="confirmRevert = true"
            >
              {{ t('hostControl.boot.params.revert.button') }}
            </button>
          </div>

          <!-- revert confirm -->
          <div
            v-if="confirmRevert"
            class="nb-card space-y-1.5 bg-brand-red/10 p-2"
            role="alertdialog"
          >
            <p class="text-xs">{{ t('hostControl.boot.params.revert.confirm') }}</p>
            <div class="flex gap-1">
              <button
                type="button"
                class="nb-btn border-brand-red text-[11px] text-brand-red"
                :disabled="busy === 'revert'"
                @click="runRevert"
              >
                {{ t('hostControl.boot.params.revert.yes') }}
              </button>
              <button type="button" class="nb-btn text-[11px]" @click="confirmRevert = false">
                {{ t('hostControl.system.cancel') }}
              </button>
            </div>
          </div>

          <!-- preview diff + warnings -->
          <template v-if="preview">
            <div v-if="!preview.diff.length" class="text-[11px] opacity-60">
              {{ t('hostControl.boot.params.preview.noDiff') }}
            </div>
            <template v-else>
              <p class="text-[11px] font-bold opacity-70">
                {{ t('hostControl.boot.params.preview.diffTitle') }} · {{ primaryName }}
              </p>
              <pre
                class="nb-card max-h-64 overflow-auto bg-paper p-2 font-mono text-[11px] leading-tight"
              ><code><span v-for="(line, i) in preview.diff" :key="i" :class="diffClass(line)" class="block">{{ line }}</span></code></pre>
              <p
                v-for="w in preview.validation.warnings"
                :key="w.code"
                class="text-[11px] text-brand-red"
              >
                ⚠
                {{
                  te('hostControl.boot.params.warn.' + w.code)
                    ? t('hostControl.boot.params.warn.' + w.code)
                    : w.message
                }}
              </p>
              <label
                v-if="preview.validation.warnings.length"
                class="flex cursor-pointer items-center gap-2 text-[11px]"
              >
                <input v-model="warnAck" type="checkbox" class="h-4 w-4 accent-ink" />
                {{ t('hostControl.boot.params.apply.warnAck') }}
              </label>
              <button
                type="button"
                class="nb-btn border-brand-red text-xs text-brand-red"
                :disabled="!canApply || busy === 'apply'"
                @click="runApply"
              >
                {{
                  busy === 'apply'
                    ? t('hostControl.boot.params.apply.applying')
                    : t('hostControl.boot.params.apply.button')
                }}
              </button>
            </template>
          </template>
        </section>
      </template>
    </template>
  </div>
</template>
