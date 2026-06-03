<script setup lang="ts">
/** Per-driver tuning recommendation (compute-only). Given the assigned motor + a supply
 *  voltage, asks the backend for a suggested run current + StealthChop/SpreadCycle
 *  registers, and shows them diffed against the live config. Applying is a later, gated
 *  step — this panel never writes to the driver.
 */
import { computed, ref } from 'vue'

import { fetchRecommendation } from './api'
import { recommendationRows } from './format'
import type { DriverRecommendation, TmcDriver } from './types'

const props = defineProps<{ driver: TmcDriver }>()

const open = ref(false)
const voltage = ref(24)
const loading = ref(false)
const error = ref<string | null>(null)
const rec = ref<DriverRecommendation | null>(null)

const rows = computed(() => (rec.value ? recommendationRows(props.driver, rec.value) : []))

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
</script>

<template>
  <div class="font-mono text-[10px]">
    <button
      class="opacity-60 transition-opacity hover:opacity-100"
      :aria-expanded="open"
      @click="open = !open"
    >
      {{ open ? '▾' : '⚙' }} recommend tuning
    </button>

    <div
      v-if="open"
      class="mt-1 space-y-1.5 rounded-brutal border-2 border-dashed border-ink bg-paper p-2"
    >
      <div class="flex items-center gap-1.5">
        <label class="opacity-70" :for="`v-${driver.stepper}`">supply</label>
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
          class="nb-btn ml-auto bg-brand-cyan px-2 py-0.5 text-[10px]"
          :disabled="loading"
          @click="compute"
        >
          {{ loading ? '…' : rec ? 'recompute' : 'recommend' }}
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
              <th class="text-left font-normal"></th>
              <th class="text-right font-normal">current</th>
              <th class="text-right font-normal">recommended</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in rows" :key="r.label" :class="r.changed ? 'text-ink' : 'opacity-60'">
              <td class="text-left">{{ r.label }}</td>
              <td class="text-right">{{ r.current ?? '—' }}</td>
              <td class="text-right font-bold" :class="{ 'text-brand-blue': r.changed }">
                {{ r.recommended }}
              </td>
            </tr>
          </tbody>
        </table>
        <p class="opacity-60">
          run current = {{ rec.run_current_basis }}; StealthChop holds to ~{{
            rec.max_pwm_rps
          }}
          rev/s at {{ rec.voltage }} V.
        </p>
        <p class="rounded-brutal border-2 border-ink bg-brand-yellow px-1.5 py-0.5">
          Preview only — nothing is written to the driver. Applying lands in a later step.
        </p>
      </template>
    </div>
  </div>
</template>
