<script setup lang="ts">
/** Advanced register editor (P10b). Lets you edit the safe subset of a driver's TMC registers
 *  live, driven entirely by the SERVER's field policy — the client never decides what's editable
 *  or the bounds (the backend clamps + rejects, because SET_TMC_FIELD silently mask-truncates).
 *  Each write is gated (refused while printing/paused), reversible (INIT_TMC / restart), and risky
 *  fields require a per-field confirm. Non-editable registers are shown read-only beneath.
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { fetchFieldPolicy, revertDriver, setCoolstep, setField } from './api'
import { stallguardRange } from './format'
import HelpNote from './HelpNote.vue'
import type { FieldPolicyEntry, FieldPolicyMap, TmcDriver } from './types'

const { t } = useI18n({ useScope: 'global' })

/** CoolStep's five coupled registers are presented as one toggle, not five raw boxes. */
const COOLSTEP_FIELDS = ['semin', 'semax', 'seup', 'sedn', 'seimin']

const props = defineProps<{ driver: TmcDriver }>()
const emit = defineEmits<{ changed: [] }>()

const open = ref(false)
const policy = ref<FieldPolicyMap | null>(null)
const loading = ref(false)
const loadErr = ref<string | null>(null)

const values = ref<Record<string, number>>({})
const confirms = ref<Record<string, boolean>>({})
const busyField = ref<string | null>(null)
const reverting = ref(false)
const coolstepBusy = ref(false)
const result = ref<{ field: string; ok: boolean; message: string } | null>(null)

/** The current value of a register, for the control's initial value + the "now" hint. */
function currentValue(field: string): number | null {
  if (field === 'stealthchop_threshold') return props.driver.stealthchop_threshold
  const v = props.driver.registers[field]
  return typeof v === 'number' ? v : null
}

/** Editable fields (CoolStep's coupled set is handled by its own toggle), safe ones first. */
const fields = computed<[string, FieldPolicyEntry][]>(() => {
  const p = policy.value
  if (!p) return []
  const rank = { safe: 0, risky: 1, dangerous: 2 }
  return Object.entries(p)
    .filter(([f]) => !COOLSTEP_FIELDS.includes(f))
    .sort((a, b) => rank[a[1].risk] - rank[b[1].risk])
})

/** CoolStep is offered (as a single toggle) when this model exposes it. */
const coolstepAvailable = computed(() => !!policy.value && 'semin' in policy.value)
/** CoolStep is on when the configured lower threshold (semin) is above zero. */
const coolstepOn = computed(() => {
  const v = props.driver.registers.semin
  return typeof v === 'number' && v > 0
})

/** A polarity/pairing hint for the trickier fields, else the policy's own note. */
function hintFor(field: string, entry: FieldPolicyEntry): string | null {
  if (field === 'sgthrs' || field === 'sg4_thrs' || field === 'sgt') {
    return stallguardRange(field).hint
  }
  if (field === 'toff') {
    return t('motorDrivers.registerEditor.toffHint')
  }
  return entry.note ?? null
}

/** Raw driver_* registers that aren't editable — shown read-only for full visibility. */
const readOnlyRegisters = computed<[string, string][]>(() => {
  const p = policy.value ?? {}
  return Object.entries(props.driver.registers)
    .filter(([k]) => !(k in p))
    .map(([k, v]) => [k, String(v)])
})

async function ensurePolicy(): Promise<void> {
  if (policy.value || loading.value) return
  loading.value = true
  loadErr.value = null
  try {
    const res = await fetchFieldPolicy(props.driver.model)
    const init: Record<string, number> = {}
    for (const [field, entry] of Object.entries(res.fields)) {
      init[field] = currentValue(field) ?? entry.min ?? 0
    }
    values.value = init
    policy.value = res.fields // set last: `fields` renders only once `values` is populated
  } catch (e) {
    loadErr.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

function toggle(): void {
  open.value = !open.value
  if (open.value) void ensurePolicy()
}

async function write(field: string): Promise<void> {
  busyField.value = field
  result.value = null
  try {
    const res = await setField(props.driver.stepper, field, values.value[field], props.driver.model)
    result.value = { field, ok: res.ok, message: res.message }
    if (res.ok) emit('changed')
  } catch (e) {
    result.value = { field, ok: false, message: e instanceof Error ? e.message : String(e) }
  } finally {
    busyField.value = null
  }
}

async function resetToConfig(): Promise<void> {
  reverting.value = true
  result.value = null
  try {
    const res = await revertDriver(props.driver.stepper)
    result.value = { field: '(all)', ok: res.ok, message: res.message }
    if (res.ok) emit('changed')
  } catch (e) {
    result.value = {
      field: '(all)',
      ok: false,
      message: e instanceof Error ? e.message : String(e),
    }
  } finally {
    reverting.value = false
  }
}

async function applyCoolstep(enable: boolean): Promise<void> {
  coolstepBusy.value = true
  result.value = null
  try {
    const res = await setCoolstep(props.driver.stepper, enable, props.driver.model)
    result.value = { field: 'coolstep', ok: res.ok, message: res.message }
    if (res.ok) emit('changed')
  } catch (e) {
    result.value = {
      field: 'coolstep',
      ok: false,
      message: e instanceof Error ? e.message : String(e),
    }
  } finally {
    coolstepBusy.value = false
  }
}

/** Options for a small-range select control (0…max, or the explicit enum). */
function selectOptions(entry: FieldPolicyEntry): number[] {
  if (entry.enum) return entry.enum
  const max = entry.max ?? 0
  return Array.from({ length: max + 1 }, (_, i) => i)
}

function canWrite(field: string, entry: FieldPolicyEntry): boolean {
  if (busyField.value) return false
  return !entry.requires_confirm || confirms.value[field] === true
}
</script>

<template>
  <div class="font-mono text-[10px]">
    <button
      class="opacity-60 transition-opacity hover:opacity-100"
      :aria-expanded="open"
      @click="toggle"
    >
      {{ open ? '▾' : '🛠' }} {{ t('motorDrivers.registerEditor.toggle') }}
    </button>

    <div
      v-if="open"
      class="mt-1 space-y-2 rounded-brutal border-2 border-dashed border-ink bg-paper p-2"
    >
      <div class="flex flex-wrap items-center justify-between gap-2">
        <HelpNote topic="registers" />
        <button
          class="nb-btn bg-surface px-2 py-0.5 text-[10px]"
          :disabled="reverting || !!busyField"
          :title="t('motorDrivers.registerEditor.resetTitle')"
          @click="resetToConfig"
        >
          {{ reverting ? '…' : t('motorDrivers.registerEditor.resetLabel') }}
        </button>
      </div>

      <p class="opacity-70">
        <i18n-t keypath="motorDrivers.registerEditor.liveOnly" tag="span" scope="global">
          <template #live>
            <b>{{ t('motorDrivers.registerEditor.liveOnlyEmphasis') }}</b>
          </template>
          <template #initTmc>
            <code>INIT_TMC</code>
          </template>
        </i18n-t>
      </p>

      <p v-if="loading" class="opacity-60">{{ t('motorDrivers.registerEditor.loading') }}</p>
      <p v-else-if="loadErr" class="text-brand-red">{{ loadErr }}</p>

      <!-- CoolStep: one toggle for the five coupled registers -->
      <div
        v-if="coolstepAvailable"
        class="flex flex-wrap items-center gap-2 border-b-2 border-dashed border-ink pb-1.5"
      >
        <span class="w-28 shrink-0">{{ t('motorDrivers.registerEditor.coolstep') }}</span>
        <span class="nb-badge" :class="coolstepOn ? 'bg-brand-lime' : 'bg-surface opacity-60'">{{
          coolstepOn ? t('motorDrivers.registerEditor.on') : t('motorDrivers.registerEditor.off')
        }}</span>
        <button
          class="nb-btn bg-brand-lime px-2 py-0.5 text-[10px]"
          :disabled="coolstepBusy"
          :title="t('motorDrivers.registerEditor.coolstepEnableTitle')"
          @click="applyCoolstep(true)"
        >
          {{ coolstepBusy ? '…' : t('motorDrivers.registerEditor.enable') }}
        </button>
        <button
          class="nb-btn bg-surface px-2 py-0.5 text-[10px]"
          :disabled="coolstepBusy"
          @click="applyCoolstep(false)"
        >
          {{ t('motorDrivers.registerEditor.off') }}
        </button>
        <HelpNote topic="coolstep" />
      </div>

      <!-- Editable fields -->
      <div
        v-for="[field, entry] in fields"
        :key="field"
        class="flex flex-wrap items-center gap-1.5"
      >
        <span class="w-28 shrink-0 truncate" :title="field">{{ field }}</span>
        <span
          v-if="entry.risk === 'risky'"
          class="nb-badge bg-brand-yellow px-1 py-0 text-[9px]"
          :title="t('motorDrivers.registerEditor.riskyTitle')"
          >!</span
        >

        <!-- control -->
        <input
          v-if="entry.control === 'toggle'"
          v-model.number="values[field]"
          type="checkbox"
          :true-value="1"
          :false-value="0"
          class="shrink-0"
        />
        <select
          v-else-if="entry.control === 'select'"
          v-model.number="values[field]"
          class="rounded-brutal border-2 border-ink bg-surface px-1 py-0.5 text-[10px]"
        >
          <option v-for="o in selectOptions(entry)" :key="o" :value="o">{{ o }}</option>
        </select>
        <input
          v-else
          v-model.number="values[field]"
          type="number"
          :min="entry.velocity ? 0 : entry.min"
          :max="entry.velocity ? undefined : entry.max"
          class="w-16 rounded-brutal border-2 border-ink bg-surface px-1 py-0.5 text-[10px]"
        />
        <span v-if="entry.velocity" class="opacity-50">mm/s</span>
        <span v-else-if="entry.min != null" class="opacity-40"
          >{{ entry.min }}…{{ entry.max }}</span
        >

        <span class="opacity-50"
          >{{ t('motorDrivers.registerEditor.now') }} {{ currentValue(field) ?? '—' }}</span
        >

        <label v-if="entry.requires_confirm" class="flex items-center gap-1">
          <input v-model="confirms[field]" type="checkbox" class="shrink-0" />
          <span class="opacity-60">{{ t('motorDrivers.registerEditor.confirm') }}</span>
        </label>

        <button
          class="nb-btn bg-brand-lime px-2 py-0.5 text-[10px]"
          :disabled="!canWrite(field, entry)"
          @click="write(field)"
        >
          {{ busyField === field ? '…' : t('motorDrivers.registerEditor.set') }}
        </button>
        <span v-if="hintFor(field, entry)" class="w-full ps-28 text-[9px] opacity-50">{{
          hintFor(field, entry)
        }}</span>
      </div>

      <p
        v-if="result"
        class="rounded-brutal border-2 border-ink px-1.5 py-0.5"
        :class="result.ok ? 'bg-brand-lime' : 'bg-brand-red text-surface'"
      >
        <b>{{ result.field }}</b
        >: {{ result.message }}
      </p>

      <!-- Read-only registers (not editable) -->
      <div v-if="readOnlyRegisters.length" class="border-t-2 border-dashed border-ink pt-1.5">
        <div class="mb-1 opacity-50">{{ t('motorDrivers.registerEditor.readOnly') }}</div>
        <dl class="grid grid-cols-2 gap-x-2 gap-y-0.5">
          <div v-for="[k, v] in readOnlyRegisters" :key="k" class="flex justify-between gap-1">
            <dt class="opacity-60">{{ k }}</dt>
            <dd class="font-bold">{{ v }}</dd>
          </div>
        </dl>
      </div>
    </div>
  </div>
</template>
