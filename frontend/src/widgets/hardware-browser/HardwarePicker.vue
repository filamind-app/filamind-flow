<script setup lang="ts" generic="T extends Record<string, unknown>">
/** DB-3d — a reusable "pick a part" control backed by the hardware DB. Generalises MotorPicker:
 *  give it a `type` (boards / drivers / motors / hosts) and it loads that canonical catalog into a
 *  typeahead `ComboSelect`, then emits the chosen id AND the full summary so a host widget can
 *  auto-fill from it (e.g. Motor Drivers pre-filling run_current). Any widget can embed it. */
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import ComboSelect from '@/components/ui/ComboSelect.vue'

import { fetchBoards, fetchDrivers, fetchHosts, fetchMotors } from './api'

type PickerType = 'boards' | 'drivers' | 'motors' | 'hosts'

const props = withDefaults(
  defineProps<{
    type: PickerType
    modelValue: string | null
    placeholder?: string
    disabled?: boolean
  }>(),
  { placeholder: '', disabled: false },
)
const emit = defineEmits<{
  'update:modelValue': [value: string | null]
  /** The full summary of the picked entity (or null when cleared) — for auto-fill. */
  select: [entity: T | null]
}>()

const { t } = useI18n({ useScope: 'global' })

const items = ref<Record<string, unknown>[]>([])
const loading = ref(false)

const ID_KEY: Record<PickerType, string> = {
  boards: 'board_id',
  drivers: 'driver_id',
  motors: 'motor_id',
  hosts: 'host_id',
}

/** Page the whole catalog of `type` (the API caps a page at 200) into one list for the typeahead. */
async function loadAll(): Promise<void> {
  loading.value = true
  const out: Record<string, unknown>[] = []
  try {
    for (let offset = 0; offset < 5000; offset += 200) {
      const params = { limit: 200, offset }
      const r =
        props.type === 'boards'
          ? await fetchBoards(params)
          : props.type === 'drivers'
            ? await fetchDrivers(params)
            : props.type === 'motors'
              ? await fetchMotors(params)
              : await fetchHosts(params)
      const list =
        (r as { boards?: unknown[]; drivers?: unknown[]; motors?: unknown[]; hosts?: unknown[] })[
          props.type
        ] ?? []
      out.push(...(list as Record<string, unknown>[]))
      if (out.length >= r.total || list.length === 0) break
    }
    items.value = out
  } catch {
    items.value = []
  } finally {
    loading.value = false
  }
}

function sublabel(e: Record<string, unknown>): string {
  const mfr = (e.manufacturer as string) || ''
  if (props.type === 'boards') return [mfr, e.boardClass].filter(Boolean).join(' · ')
  if (props.type === 'drivers') return [mfr, e.interface].filter(Boolean).join(' · ')
  if (props.type === 'hosts') return [mfr, e.kind].filter(Boolean).join(' · ')
  // motors
  const nema = e.nema ? `NEMA ${e.nema}` : ''
  const run = e.recommendedRunCurrent ? `${e.recommendedRunCurrent} A` : ''
  return [mfr, nema, run].filter(Boolean).join(' · ')
}

const options = computed(() =>
  items.value.map((e) => ({
    value: String(e[ID_KEY[props.type]]),
    label: String(e.name || e.display_name || e.model || e[ID_KEY[props.type]]),
    sublabel: sublabel(e),
  })),
)

function onPick(id: string | null): void {
  emit('update:modelValue', id)
  const found = (items.value.find((e) => String(e[ID_KEY[props.type]]) === id) ?? null) as T | null
  emit('select', id ? found : null)
}

watch(() => props.type, loadAll)
onMounted(loadAll)
</script>

<template>
  <ComboSelect
    :model-value="modelValue"
    :options="options"
    :placeholder="placeholder || t('hardwareBrowser.picker.placeholder')"
    :disabled="disabled || loading"
    clearable
    @update:model-value="onPick"
  />
</template>
