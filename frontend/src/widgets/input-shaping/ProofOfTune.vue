<script setup lang="ts">
/** Proof of tune — pick a before and an after shaper result on one axis and see what
 *  actually changed: grade, remaining vibration, smoothing, usable accel. Copyable as
 *  plain text. Pure presentation over the merged audit records the Audit tab already has.
 */
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { AuditRecord } from './audit'
import { buildProofRows, proofCandidates, proofText } from './proof'

const props = defineProps<{ records: AuditRecord[] }>()

const { t } = useI18n({ useScope: 'global' })

const axis = ref<'x' | 'y'>('x')
const beforeId = ref<string | null>(null)
const afterId = ref<string | null>(null)
const copied = ref(false)

const candidates = computed(() => proofCandidates(props.records, axis.value))

// Defaults: oldest candidate = before, newest = after (the natural tuning story).
watch(
  [candidates, axis],
  () => {
    const list = candidates.value
    if (!list.some((r) => r.id === beforeId.value))
      beforeId.value = list.length > 1 ? list[list.length - 1].id : null
    if (!list.some((r) => r.id === afterId.value)) afterId.value = list.length ? list[0].id : null
  },
  { immediate: true },
)

const before = computed(() => candidates.value.find((r) => r.id === beforeId.value) ?? null)
const after = computed(() => candidates.value.find((r) => r.id === afterId.value) ?? null)
const rows = computed(() =>
  before.value && after.value && before.value.id !== after.value.id
    ? buildProofRows(before.value, after.value)
    : [],
)

function fmtDate(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}
function optionLabel(r: AuditRecord): string {
  const grade = r.grade ? ` · ${r.grade.letter} (${r.grade.score})` : ''
  return `${fmtDate(r.at)}${grade}`
}
function deltaClass(better: boolean | null): string {
  if (better === true) return 'text-brand-lime'
  if (better === false) return 'text-brand-red'
  return 'opacity-50'
}

async function copyReport(): Promise<void> {
  if (!before.value || !after.value || !rows.value.length) return
  const text = proofText(
    t('inputShaping.proof.title'),
    axis.value,
    fmtDate(before.value.at),
    fmtDate(after.value.at),
    rows.value.map((row) => ({ label: t(`inputShaping.proof.metric.${row.key}`), row })),
  )
  try {
    await navigator.clipboard?.writeText(text)
    copied.value = true
    setTimeout(() => (copied.value = false), 1500)
  } catch {
    /* clipboard unavailable */
  }
}
</script>

<template>
  <div class="space-y-2 rounded-brutal border-2 border-ink p-2">
    <div class="flex flex-wrap items-center gap-2">
      <span class="text-[11px] font-bold uppercase tracking-wide"
        >📊 {{ t('inputShaping.proof.title') }}</span
      >
      <div class="flex gap-1">
        <button
          v-for="a in ['x', 'y'] as const"
          :key="a"
          type="button"
          class="nb-btn px-2 py-0.5 text-[11px]"
          :class="axis === a ? 'bg-brand-cyan' : 'bg-surface'"
          @click="axis = a"
        >
          {{ a.toUpperCase() }}
        </button>
      </div>
      <span class="flex-1"></span>
      <button
        v-if="rows.length"
        type="button"
        class="nb-btn bg-surface px-2 py-0.5 text-[11px]"
        @click="copyReport"
      >
        {{ copied ? t('inputShaping.proof.copied') : t('inputShaping.proof.copy') }}
      </button>
    </div>

    <p v-if="candidates.length < 2" class="text-[11px] opacity-70">
      {{ t('inputShaping.proof.empty') }}
    </p>

    <template v-else>
      <div class="grid gap-2 sm:grid-cols-2">
        <label class="space-y-0.5 text-[10px]">
          <span class="font-bold uppercase opacity-70">{{ t('inputShaping.proof.before') }}</span>
          <select v-model="beforeId" class="nb-input w-full px-1.5 py-0.5 text-[11px]">
            <option v-for="r in candidates" :key="r.id" :value="r.id">{{ optionLabel(r) }}</option>
          </select>
        </label>
        <label class="space-y-0.5 text-[10px]">
          <span class="font-bold uppercase opacity-70">{{ t('inputShaping.proof.after') }}</span>
          <select v-model="afterId" class="nb-input w-full px-1.5 py-0.5 text-[11px]">
            <option v-for="r in candidates" :key="r.id" :value="r.id">{{ optionLabel(r) }}</option>
          </select>
        </label>
      </div>

      <p v-if="beforeId === afterId" class="text-[11px] opacity-70">
        {{ t('inputShaping.proof.samePick') }}
      </p>

      <table v-else-if="rows.length" class="w-full border-collapse font-mono text-[10px]">
        <thead>
          <tr class="border-b-2 border-ink text-start">
            <th class="pe-2 text-start">{{ t('inputShaping.proof.metricHead') }}</th>
            <th class="pe-2 text-start">{{ t('inputShaping.proof.before') }}</th>
            <th class="pe-2 text-start">{{ t('inputShaping.proof.after') }}</th>
            <th class="text-start">{{ t('inputShaping.proof.delta') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.key" class="border-b border-ink/20">
            <td class="pe-2 opacity-70">{{ t(`inputShaping.proof.metric.${row.key}`) }}</td>
            <td class="pe-2">{{ row.before }}</td>
            <td class="pe-2 font-bold">{{ row.after }}</td>
            <td :class="deltaClass(row.better)">{{ row.delta || '—' }}</td>
          </tr>
        </tbody>
      </table>
    </template>
  </div>
</template>
