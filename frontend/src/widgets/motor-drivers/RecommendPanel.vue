<script setup lang="ts">
/** Per-driver tuning recommendation + apply. Given the assigned motor + a supply voltage,
 *  asks the backend for a suggested run current + StealthChop/SpreadCycle registers, shown
 *  diffed against the live config. The values can then be copied to printer.cfg, or written
 *  live (SET_TMC_*) behind an explicit confirm — and reverted (INIT_TMC). Writes are gated
 *  server-side too (refused while printing).
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import {
  applyTuning,
  fetchConfigBlock,
  fetchRecommendation,
  revertDriver,
  runAutotune,
} from './api'
import { recommendationRows } from './format'
import type { DriverRecommendation, TmcDriver } from './types'

const { t } = useI18n({ useScope: 'global' })

const props = defineProps<{ driver: TmcDriver; defaultOpen?: boolean }>()
const emit = defineEmits<{ applied: [] }>()

const open = ref(props.defaultOpen === true)
const voltage = ref(24)
const loading = ref(false)
const error = ref<string | null>(null)
const rec = ref<DriverRecommendation | null>(null)

const confirmed = ref(false)
const busy = ref(false)
const resultMsg = ref<string | null>(null)
const resultOk = ref(false)
const configText = ref<string | null>(null)

const rows = computed(() => (rec.value ? recommendationRows(props.driver, rec.value) : []))

/** The recommended register values as a SET_TMC_FIELD map. */
function recFields(): Record<string, number> {
  const r = rec.value
  return r ? { pwm_grad: r.pwm_grad, pwm_ofs: r.pwm_ofs, hstrt: r.hstrt, hend: r.hend } : {}
}

async function compute(): Promise<void> {
  if (!props.driver.motor) return
  loading.value = true
  error.value = null
  try {
    rec.value = await fetchRecommendation({
      motor_model: props.driver.motor.model,
      voltage: voltage.value,
      is_2240: props.driver.model === 'tmc2240',
    })
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

/** Wraps a write/revert action: show its message, and refresh the dashboard on success. */
async function run(action: () => Promise<{ ok: boolean; message: string }>): Promise<void> {
  busy.value = true
  resultMsg.value = null
  try {
    const res = await action()
    resultOk.value = res.ok
    resultMsg.value = res.message
    if (res.ok) emit('applied')
  } catch (e) {
    resultOk.value = false
    resultMsg.value = e instanceof Error ? e.message : String(e)
  } finally {
    busy.value = false
  }
}

function apply(): Promise<void> {
  const r = rec.value
  if (!r) return Promise.resolve()
  return run(() =>
    applyTuning({ stepper: props.driver.stepper, run_current: r.run_current, fields: recFields() }),
  )
}

function revert(): Promise<void> {
  return run(() => revertDriver(props.driver.stepper))
}

function autotune(): Promise<void> {
  return run(() => runAutotune(props.driver.stepper))
}

async function copyConfig(): Promise<void> {
  const r = rec.value
  if (!r || !props.driver.motor) return
  try {
    const { text } = await fetchConfigBlock({
      stepper: props.driver.stepper,
      model: props.driver.model,
      run_current: r.run_current,
      fields: recFields(),
    })
    configText.value = text
    await navigator.clipboard?.writeText(text).catch(() => {})
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
}
</script>

<template>
  <div class="font-mono text-[10px]">
    <button
      class="opacity-60 transition-opacity hover:opacity-100"
      :aria-expanded="open"
      @click="open = !open"
    >
      {{ open ? '▾' : '⚙' }} {{ t('motorDrivers.recommendPanel.toggle') }}
    </button>

    <div
      v-if="open"
      class="mt-1 space-y-1.5 rounded-brutal border-2 border-dashed border-ink bg-paper p-2"
    >
      <div class="flex items-center gap-1.5">
        <label class="opacity-70" :for="`v-${driver.stepper}`">{{
          t('motorDrivers.recommendPanel.supply')
        }}</label>
        <input
          :id="`v-${driver.stepper}`"
          v-model.number="voltage"
          type="number"
          min="0"
          max="60"
          step="0.1"
          class="w-16 rounded-brutal border-2 border-ink bg-surface px-1 py-0.5 text-[10px]"
        />
        <span class="opacity-70">V</span>
        <button
          class="nb-btn ms-auto bg-brand-cyan px-2 py-0.5 text-[10px]"
          :disabled="loading"
          @click="compute"
        >
          {{
            loading
              ? '…'
              : rec
                ? t('motorDrivers.recommendPanel.recompute')
                : t('motorDrivers.recommendPanel.recommend')
          }}
        </button>
      </div>

      <p
        v-if="error"
        class="rounded-brutal border-2 border-ink bg-brand-red px-1.5 py-0.5 text-surface"
      >
        {{ error }}
      </p>

      <template v-if="rec">
        <table class="w-full">
          <thead class="opacity-60">
            <tr>
              <th class="text-start font-normal"></th>
              <th class="text-end font-normal">
                {{ t('motorDrivers.recommendPanel.colCurrent') }}
              </th>
              <th class="text-end font-normal">
                {{ t('motorDrivers.recommendPanel.colRecommended') }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in rows" :key="r.label" :class="r.changed ? 'text-ink' : 'opacity-60'">
              <td class="text-start">{{ r.label }}</td>
              <td class="text-end">{{ r.current ?? '—' }}</td>
              <td class="text-end font-bold" :class="{ 'text-brand-blue': r.changed }">
                {{ r.recommended }}
              </td>
            </tr>
          </tbody>
        </table>
        <p class="opacity-60">
          {{
            t('motorDrivers.recommendPanel.basis', {
              basis: rec.run_current_basis,
              rps: rec.max_pwm_rps,
              voltage: rec.voltage,
            })
          }}
        </p>
        <!-- Apply: copy-to-config (safe) or a gated live write -->
        <div class="space-y-1 border-t-2 border-dashed border-ink pt-1.5">
          <label class="flex items-start gap-1.5">
            <input v-model="confirmed" type="checkbox" class="mt-0.5 shrink-0" />
            <span>
              <i18n-t keypath="motorDrivers.recommendPanel.confirm" tag="span" scope="global">
                <template #stepper
                  ><b>{{ driver.stepper }}</b></template
                >
              </i18n-t>
            </span>
          </label>
          <div class="flex flex-wrap items-center gap-1.5">
            <button
              class="nb-btn bg-brand-lime px-2 py-0.5 text-[10px]"
              :disabled="!confirmed || busy"
              @click="apply"
            >
              {{ busy ? '…' : t('motorDrivers.recommendPanel.applyToDriver') }}
            </button>
            <button
              class="nb-btn bg-surface px-2 py-0.5 text-[10px]"
              :disabled="busy"
              @click="revert"
            >
              {{ t('motorDrivers.recommendPanel.revert') }}
            </button>
            <button
              class="nb-btn bg-surface px-2 py-0.5 text-[10px]"
              :disabled="busy"
              @click="copyConfig"
            >
              {{ t('motorDrivers.recommendPanel.copyConfig') }}
            </button>
            <button
              class="nb-btn bg-surface px-2 py-0.5 text-[10px]"
              :disabled="busy"
              :title="t('motorDrivers.recommendPanel.autotuneTitle')"
              @click="autotune"
            >
              {{ t('motorDrivers.recommendPanel.autotune') }}
            </button>
          </div>
          <p
            v-if="resultMsg"
            class="rounded-brutal border-2 border-ink px-1.5 py-0.5"
            :class="resultOk ? 'bg-brand-lime' : 'bg-brand-red text-surface'"
          >
            {{ resultMsg }}
          </p>
          <pre
            v-if="configText"
            class="overflow-x-auto rounded-brutal border-2 border-ink bg-surface p-1.5 text-[9px] leading-tight"
            >{{ configText }}</pre
          >
        </div>
      </template>
    </div>
  </div>
</template>
