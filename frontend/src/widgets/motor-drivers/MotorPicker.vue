<script setup lang="ts">
/** Per-stepper motor picker: shows the assigned motor (+ specs) and a dropdown/combobox to
 *  choose from the catalogued motors (#120 — a typeahead `<ComboSelect>`, not an inline list,
 *  the convention for long pickers). Emits `assign` (stepper, model | null); the parent persists
 *  it and refreshes.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import ComboSelect from '@/components/ui/ComboSelect.vue'

import { motorSpecLabel } from './format'
import type { MotorSpec } from './types'

const { t } = useI18n({ useScope: 'global' })

const props = defineProps<{
  stepper: string
  assigned: MotorSpec | null
  catalog: MotorSpec[]
}>()
const emit = defineEmits<{ assign: [stepper: string, model: string | null] }>()

/** Catalog -> combobox options (label = model, sublabel = maker + key specs). */
const options = computed(() =>
  props.catalog.map((m) => ({
    value: m.model,
    label: m.model,
    sublabel: `${m.manufacturer} · ${motorSpecLabel(m)}`,
  })),
)
const selectedModel = computed(() => props.assigned?.model ?? null)
</script>

<template>
  <div class="font-mono text-[11px]">
    <div class="mb-1 min-w-0 truncate">
      <span class="opacity-60">{{ t('motorDrivers.motorPicker.motorLabel') }}</span>
      <b v-if="assigned"> {{ assigned.manufacturer }} {{ assigned.model }}</b>
      <span v-else class="opacity-60"> {{ t('motorDrivers.motorPicker.notSet') }}</span>
    </div>
    <div v-if="assigned" class="mb-1 truncate opacity-70">{{ motorSpecLabel(assigned) }}</div>
    <ComboSelect
      :model-value="selectedModel"
      :options="options"
      :placeholder="t('motorDrivers.motorPicker.searchPlaceholder')"
      clearable
      @update:model-value="(m) => emit('assign', stepper, m)"
    />
  </div>
</template>
