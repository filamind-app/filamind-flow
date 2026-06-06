<script setup lang="ts">
/** Sensorless-homing StallGuard tuner. Set the StallGuard threshold and test-home one axis.
 *  Both actions are gated: an explicit confirm here, and refused server-side while printing.
 *  Test-home moves the toolhead and — with a wrong threshold — may not stop, so it carries a
 *  loud crash warning. Rendered (by HomingPanel / the wizard) only for sensorless axes; the
 *  threshold range + polarity hint adapt to the model's register (sgthrs/sg4_thrs vs signed sgt).
 */
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { homeAxis, setStallguard } from './api'
import { applyResultText, stallguardRange } from './format'
import type { ApplyResponse, TmcDriver } from './types'

const { t } = useI18n({ useScope: 'global' })

const props = defineProps<{ driver: TmcDriver }>()
const emit = defineEmits<{ changed: [] }>()

const range = stallguardRange(props.driver.stallguard_field)
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
    msg.value = applyResultText(res)
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
  <div
    class="space-y-1.5 rounded-brutal border-2 border-dashed border-ink bg-paper p-2 font-mono text-[10px]"
  >
    <p v-if="!driver.stallguard_field" class="text-brand-red">
      {{ t('motorDrivers.sensorless.noRegister') }}
    </p>
    <p class="opacity-70">
      <i18n-t keypath="motorDrivers.sensorless.intro" tag="span" scope="global">
        <template #field
          ><b>{{ driver.stallguard_field ?? '—' }}</b></template
        >
      </i18n-t>
      {{ range.hint }}
    </p>

    <div class="flex items-center gap-1.5">
      <label class="opacity-70" :for="`sg-${driver.stepper}`">{{
        t('motorDrivers.sensorless.threshold')
      }}</label>
      <input
        :id="`sg-${driver.stepper}`"
        v-model.number="threshold"
        type="number"
        :min="range.min"
        :max="range.max"
        :disabled="!driver.stallguard_field"
        class="w-16 rounded-brutal border-2 border-ink bg-surface px-1 py-0.5 text-[10px]"
      />
      <span class="opacity-60">{{
        t('motorDrivers.sensorless.nowRange', {
          now: driver.stallguard_threshold ?? '—',
          min: range.min,
          max: range.max,
        })
      }}</span>
    </div>
    <label class="flex items-start gap-1.5">
      <input v-model="confirmSet" type="checkbox" class="mt-0.5 shrink-0" />
      <span>{{ t('motorDrivers.sensorless.confirmSet') }}</span>
    </label>
    <button
      class="nb-btn bg-brand-lime px-2 py-0.5 text-[10px]"
      :disabled="!confirmSet || busy || !driver.stallguard_field"
      @click="setThreshold"
    >
      {{ busy ? '…' : t('motorDrivers.sensorless.setThreshold') }}
    </button>

    <template v-if="axis">
      <div class="rounded-brutal border-2 border-ink bg-brand-red px-1.5 py-1 text-surface">
        <i18n-t keypath="motorDrivers.sensorless.testHomeWarning" tag="span" scope="global">
          <template #axis
            ><b>{{ axis }}</b></template
          >
        </i18n-t>
      </div>
      <label class="flex items-start gap-1.5">
        <input v-model="confirmHome" type="checkbox" class="mt-0.5 shrink-0" />
        <span>{{ t('motorDrivers.sensorless.confirmHome', { axis }) }}</span>
      </label>
      <button
        class="nb-btn bg-brand-yellow px-2 py-0.5 text-[10px]"
        :disabled="!confirmHome || busy"
        @click="testHome"
      >
        {{ busy ? '…' : t('motorDrivers.sensorless.testHome', { axis }) }}
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
</template>
