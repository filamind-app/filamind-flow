<script setup lang="ts">
/** Per-axis homing panel (P9). Adapts to how the axis actually homes — read from the Klipper
 *  config (`homing_method`), not guessed from "has a StallGuard register":
 *    • sensorless    → the StallGuard tuner (SensorlessPanel)
 *    • physical      → live endstop-switch state + a plain test-home
 *    • probe         → a pointer to the Z-probe / bed-mesh tools (no StallGuard to tune)
 *    • other_virtual → a note (a virtual endstop managed by its own host module)
 *  Extra motors on a shared rail (`inherited`) get no panel — they don't home on their own.
 */
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { fetchEndstops, homeAxis } from './api'
import { applyResultText, endstopStateFor, homingMethodLabel } from './format'
import SensorlessPanel from './SensorlessPanel.vue'
import type { ApplyResponse, TmcDriver } from './types'

const props = defineProps<{ driver: TmcDriver }>()
const emit = defineEmits<{ changed: [] }>()

const { t } = useI18n({ useScope: 'global' })

const open = ref(false)
const method = props.driver.homing_method
const axis = props.driver.axis && /^[XYZ]$/.test(props.driver.axis) ? props.driver.axis : null

// Physical-endstop live state — queried on demand (the query uses the g-code mutex, so we
// never poll it; we read it when the panel opens and on an explicit re-check).
const endstopState = ref<string | null>(null)
const endstopErr = ref<string | null>(null)
const checking = ref(false)

async function checkEndstop(): Promise<void> {
  checking.value = true
  endstopErr.value = null
  try {
    const res = await fetchEndstops()
    endstopState.value = endstopStateFor(res.states, props.driver.stepper, axis)
    if (!res.reachable) endstopErr.value = t('motorDrivers.homing.unreachable')
  } catch (e) {
    endstopErr.value = e instanceof Error ? e.message : String(e)
  } finally {
    checking.value = false
  }
}

// Plain test-home for a physical axis — the switch stops the move, so the crash risk is far
// lower than a sensorless home (which carries its own loud warning inside SensorlessPanel).
const confirmHome = ref(false)
const homing = ref(false)
const homeMsg = ref<string | null>(null)
const homeOk = ref(false)

async function testHome(): Promise<void> {
  if (!axis) return
  homing.value = true
  homeMsg.value = null
  try {
    const res: ApplyResponse = await homeAxis(axis)
    homeOk.value = res.ok
    homeMsg.value = applyResultText(res)
    if (res.ok) emit('changed')
  } catch (e) {
    homeOk.value = false
    homeMsg.value = e instanceof Error ? e.message : String(e)
  } finally {
    homing.value = false
  }
}

function toggle(): void {
  open.value = !open.value
  if (open.value && method === 'physical' && endstopState.value === null) void checkEndstop()
}
</script>

<template>
  <div class="font-mono text-[10px]">
    <button
      class="opacity-60 transition-opacity hover:opacity-100"
      :aria-expanded="open"
      @click="toggle"
    >
      {{ open ? '▾' : '🏠' }} {{ t('motorDrivers.homing.homing') }}
      <span class="opacity-70">· {{ homingMethodLabel(method) }}</span>
    </button>

    <div v-if="open" class="mt-1">
      <!-- Sensorless: the StallGuard tuner -->
      <template v-if="method === 'sensorless'">
        <p
          v-if="driver.homing_note"
          class="mb-1 rounded-brutal border-2 border-ink bg-brand-red px-1.5 py-0.5 text-surface"
        >
          ⚠ {{ driver.homing_note }}
        </p>
        <SensorlessPanel :driver="driver" @changed="emit('changed')" />
      </template>

      <!-- Physical endstop: live switch state + a plain test-home -->
      <div
        v-else-if="method === 'physical'"
        class="space-y-1.5 rounded-brutal border-2 border-dashed border-ink bg-paper p-2"
      >
        <p class="opacity-70">
          {{ t('motorDrivers.homing.physicalIntroLead')
          }}{{ driver.homing_note ? ` (${driver.homing_note})` : ''
          }}{{ t('motorDrivers.homing.physicalIntroTail') }}
        </p>
        <div class="flex flex-wrap items-center gap-2">
          <span class="opacity-70">{{ t('motorDrivers.homing.switchLabel') }}</span>
          <span
            class="nb-badge"
            :class="endstopState === 'TRIGGERED' ? 'bg-brand-lime' : 'bg-surface'"
            >{{ endstopState ?? '—' }}</span
          >
          <button
            class="nb-btn bg-surface px-2 py-0.5 text-[10px]"
            :disabled="checking"
            @click="checkEndstop"
          >
            {{ checking ? '…' : t('motorDrivers.homing.check') }}
          </button>
          <span v-if="endstopErr" class="text-brand-red">{{ endstopErr }}</span>
        </div>

        <template v-if="axis">
          <i18n-t
            keypath="motorDrivers.homing.testHomeWarn"
            tag="div"
            scope="global"
            class="rounded-brutal border-2 border-ink bg-brand-yellow px-1.5 py-1"
          >
            <template #axis
              ><b>{{ axis }}</b></template
            >
          </i18n-t>
          <label class="flex items-start gap-1.5">
            <input v-model="confirmHome" type="checkbox" class="mt-0.5 shrink-0" />
            <span>{{ t('motorDrivers.homing.pathClear', { axis }) }}</span>
          </label>
          <button
            class="nb-btn bg-brand-lime px-2 py-0.5 text-[10px]"
            :disabled="!confirmHome || homing"
            @click="testHome"
          >
            {{ homing ? '…' : t('motorDrivers.homing.testHome', { axis }) }}
          </button>
          <p
            v-if="homeMsg"
            class="rounded-brutal border-2 border-ink px-1.5 py-0.5"
            :class="homeOk ? 'bg-brand-lime' : 'bg-brand-red text-surface'"
          >
            {{ homeMsg }}
          </p>
        </template>
      </div>

      <!-- Probe-homed Z -->
      <div
        v-else-if="method === 'probe'"
        class="rounded-brutal border-2 border-dashed border-ink bg-paper p-2 opacity-80"
      >
        {{ t('motorDrivers.homing.probeNote') }}
      </div>

      <!-- A virtual endstop that isn't a TMC StallGuard pin -->
      <div
        v-else-if="method === 'other_virtual'"
        class="rounded-brutal border-2 border-dashed border-ink bg-paper p-2 opacity-80"
      >
        {{ t('motorDrivers.homing.virtualNote') }}
      </div>
    </div>
  </div>
</template>
