<script setup lang="ts">
/** Sensorless-homing helper (P5). Tune the StallGuard threshold and test-home one axis.
 *  Both actions are gated: an explicit confirm here, and refused server-side while printing.
 *  Test-home moves the toolhead and — with a wrong threshold — may not stop, so it carries a
 *  loud crash warning. Shown only for drivers that actually support sensorless homing.
 */
import { ref } from 'vue'

import { homeAxis, setStallguard } from './api'
import type { ApplyResponse, TmcDriver } from './types'

const props = defineProps<{ driver: TmcDriver; defaultOpen?: boolean }>()
const emit = defineEmits<{ changed: [] }>()

const open = ref(props.defaultOpen === true)
const threshold = ref<number>(props.driver.stallguard_threshold ?? 0)
const confirmSet = ref(false)
const confirmHome = ref(false)
const busy = ref(false)
const msg = ref<string | null>(null)
const ok = ref(false)

//: Only offer a test-home for a single linear axis we can address with G28.
const axis = props.driver.axis && /^[XYZ]$/.test(props.driver.axis) ? props.driver.axis : null

async function run(action: () => Promise<ApplyResponse>): Promise<void> {
  busy.value = true
  msg.value = null
  try {
    const res = await action()
    ok.value = res.ok
    msg.value = res.message
    if (res.ok) emit('changed')
  } catch (e) {
    ok.value = false
    msg.value = e instanceof Error ? e.message : String(e)
  } finally {
    busy.value = false
  }
}

function setThreshold(): Promise<void> {
  const field = props.driver.stallguard_field
  if (!field) return Promise.resolve()
  return run(() => setStallguard(props.driver.stepper, field, threshold.value))
}

function testHome(): Promise<void> {
  if (!axis) return Promise.resolve()
  return run(() => homeAxis(axis))
}
</script>

<template>
  <div class="font-mono text-[10px]">
    <button
      class="opacity-60 transition-opacity hover:opacity-100"
      :aria-expanded="open"
      @click="open = !open"
    >
      {{ open ? '▾' : '🧲' }} sensorless homing
    </button>

    <div
      v-if="open"
      class="mt-1 space-y-1.5 rounded-brutal border-2 border-dashed border-ink bg-paper p-2"
    >
      <p class="opacity-70">
        StallGuard <b>{{ driver.stallguard_field }}</b> sets sensorless-homing sensitivity. Lower it
        if the axis stops too early; raise it if it doesn’t stop. Skip this if your axis homes with
        an endstop switch.
      </p>

      <div class="flex items-center gap-1.5">
        <label class="opacity-70" :for="`sg-${driver.stepper}`">threshold</label>
        <input
          :id="`sg-${driver.stepper}`"
          v-model.number="threshold"
          type="number"
          min="0"
          max="255"
          class="w-16 rounded-brutal border-2 border-ink bg-surface px-1 py-0.5 text-[10px]"
        />
        <span class="opacity-60">now: {{ driver.stallguard_threshold ?? '—' }}</span>
      </div>
      <label class="flex items-start gap-1.5">
        <input v-model="confirmSet" type="checkbox" class="mt-0.5 shrink-0" />
        <span>Write this threshold to the driver now (reversible; refused while printing).</span>
      </label>
      <button
        class="nb-btn bg-brand-lime px-2 py-0.5 text-[10px]"
        :disabled="!confirmSet || busy"
        @click="setThreshold"
      >
        {{ busy ? '…' : 'set threshold' }}
      </button>

      <template v-if="axis">
        <div class="rounded-brutal border-2 border-ink bg-brand-red px-1.5 py-1 text-surface">
          ⚠ Test-home moves the <b>{{ axis }}</b> axis now. With a wrong threshold it may not stop —
          keep a hand on the power. Sensorless axes only.
        </div>
        <label class="flex items-start gap-1.5">
          <input v-model="confirmHome" type="checkbox" class="mt-0.5 shrink-0" />
          <span>I’m watching the printer and ready to cut power — home {{ axis }}.</span>
        </label>
        <button
          class="nb-btn bg-brand-yellow px-2 py-0.5 text-[10px]"
          :disabled="!confirmHome || busy"
          @click="testHome"
        >
          {{ busy ? '…' : `test-home ${axis}` }}
        </button>
      </template>

      <p
        v-if="msg"
        class="rounded-brutal border-2 border-ink px-1.5 py-0.5"
        :class="ok ? 'bg-brand-lime' : 'bg-brand-red text-surface'"
      >
        {{ msg }}
      </p>
    </div>
  </div>
</template>
