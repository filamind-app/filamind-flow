<script setup lang="ts">
/** Guided driver-tuning wizard (P7). Walks one driver through the existing steps —
 *  choose → assign motor → recommend & apply → (sensorless) → done — reusing the same
 *  panels the dashboard uses, so there's one source of truth and the same safety gating.
 */
import { computed, ref } from 'vue'

import { saveMotorAssignment } from './api'
import { axisHeading, driverModelLabel } from './format'
import LiveMonitor from './LiveMonitor.vue'
import MotorPicker from './MotorPicker.vue'
import RecommendPanel from './RecommendPanel.vue'
import SensorlessPanel from './SensorlessPanel.vue'
import type { MotorSpec, TmcDriver } from './types'

const props = defineProps<{ drivers: TmcDriver[]; catalog: MotorSpec[] }>()
const emit = defineEmits<{ changed: []; exit: [] }>()

const step = ref(1)
const selectedStepper = ref<string | null>(null)

const selected = computed(
  () => props.drivers.find((d) => d.stepper === selectedStepper.value) ?? null,
)
const supportsSensorless = computed(
  () => !!(selected.value?.stallguard_field && selected.value?.info?.sensorless),
)

//: Labelled steps, with the sensorless step dropped when the driver can't do it.
const stepLabels = computed(() => {
  const labels = ['Choose', 'Motor', 'Tune']
  if (supportsSensorless.value) labels.push('Sensorless')
  labels.push('Done')
  return labels
})

function choose(stepper: string): void {
  selectedStepper.value = stepper
  step.value = 2
}

function next(): void {
  if (step.value === 3 && !supportsSensorless.value) step.value = 5
  else step.value = Math.min(step.value + 1, 5)
}

function back(): void {
  if (step.value === 5 && !supportsSensorless.value) step.value = 3
  else step.value = Math.max(step.value - 1, 1)
}

function restart(): void {
  selectedStepper.value = null
  step.value = 1
}

async function onAssign(stepper: string, model: string | null): Promise<void> {
  await saveMotorAssignment(stepper, model)
  emit('changed')
}
</script>

<template>
  <div class="space-y-2 text-sm">
    <div class="flex items-center justify-between gap-2">
      <div class="font-bold">🧭 Guided tuning</div>
      <button class="font-mono text-[10px] opacity-60 hover:opacity-100" @click="emit('exit')">
        ← dashboard
      </button>
    </div>

    <!-- Step breadcrumb -->
    <div class="flex flex-wrap gap-1 font-mono text-[10px]">
      <span
        v-for="(label, i) in stepLabels"
        :key="label"
        class="rounded-brutal border-2 border-ink px-1.5 py-0.5"
        :class="
          (supportsSensorless ? step - 1 : step <= 3 ? step - 1 : step - 2) === i
            ? 'bg-brand-cyan'
            : 'bg-surface opacity-60'
        "
        >{{ i + 1 }}. {{ label }}</span
      >
    </div>

    <!-- Step 1 — choose a driver -->
    <div v-if="step === 1" class="space-y-1.5">
      <p class="text-xs opacity-70">Pick the axis to tune.</p>
      <div class="grid gap-1.5 sm:grid-cols-2">
        <button
          v-for="d in drivers"
          :key="d.stepper"
          class="nb-btn justify-between bg-surface px-2 py-1 text-left text-xs"
          @click="choose(d.stepper)"
        >
          <span class="font-bold">{{ axisHeading(d) }}</span>
          <span class="font-mono text-[10px] opacity-60">{{ driverModelLabel(d.model) }}</span>
        </button>
      </div>
    </div>

    <!-- Steps 2–5 operate on the selected driver -->
    <template v-else-if="selected">
      <div class="font-mono text-[11px] opacity-70">
        Tuning <b>{{ axisHeading(selected) }}</b> · {{ driverModelLabel(selected.model) }}
      </div>

      <div v-if="step === 2" class="space-y-1.5">
        <p class="text-xs opacity-70">
          Which motor is wired to this axis? Pick it so FilaMind knows its datasheet specs.
        </p>
        <MotorPicker
          :stepper="selected.stepper"
          :assigned="selected.motor"
          :catalog="catalog"
          :default-open="true"
          @assign="onAssign"
        />
        <p v-if="!selected.motor" class="font-mono text-[10px] opacity-60">
          Assign a motor to continue.
        </p>
      </div>

      <div v-else-if="step === 3" class="space-y-1.5">
        <p class="text-xs opacity-70">
          Get a recommendation from the motor's specs, then copy it to your config or apply it live
          (gated).
        </p>
        <RecommendPanel :driver="selected" :default-open="true" @applied="emit('changed')" />
      </div>

      <div v-else-if="step === 4 && supportsSensorless" class="space-y-1.5">
        <p class="text-xs opacity-70">
          Optional: dial in sensorless homing. Skip if this axis uses an endstop switch.
        </p>
        <SensorlessPanel :driver="selected" :default-open="true" @changed="emit('changed')" />
      </div>

      <div v-else-if="step === 5" class="space-y-1.5">
        <p class="text-xs opacity-70">
          Done with <b>{{ axisHeading(selected) }}</b
          >. Watch it live while you move the axis, or tune another.
        </p>
        <LiveMonitor :driver="selected" />
        <button class="nb-btn bg-surface px-2 py-0.5 text-[10px]" @click="restart">
          tune another axis
        </button>
      </div>

      <!-- Step navigation -->
      <div class="flex items-center justify-between pt-1">
        <button class="nb-btn bg-surface px-2 py-0.5 text-[10px]" @click="back">← back</button>
        <button
          v-if="step < 5"
          class="nb-btn bg-brand-lime px-2 py-0.5 text-[10px]"
          :disabled="step === 2 && !selected.motor"
          @click="next"
        >
          next →
        </button>
        <button v-else class="nb-btn bg-brand-cyan px-2 py-0.5 text-[10px]" @click="emit('exit')">
          finish
        </button>
      </div>
    </template>
  </div>
</template>
