<script setup lang="ts">
/** Add / edit a manual topology node the auto-detection missed: an MCU/board, a USB-CAN adapter,
 *  or a host display. A small overlay form; the parent persists the result via the API and refreshes
 *  the map. Only the fields for the chosen kind are shown + validated. */
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import HardwarePicker from '@/widgets/hardware-browser/HardwarePicker.vue'

import type { ManualAddition } from './types'

const props = defineProps<{
  open: boolean
  /** When set, the form edits this existing entry instead of adding a new one. */
  entry: ManualAddition | null
  busy: boolean
}>()
const emit = defineEmits<{ close: []; submit: [entry: ManualAddition] }>()

const { t } = useI18n({ useScope: 'global' })

const kind = ref<'mcu' | 'canbus' | 'display'>('mcu')
const name = ref('')
const boardId = ref<string | null>(null)
const connection = ref('unknown')
const iface = ref('')
const displayKind = ref<'touch' | 'knomi' | 'other'>('touch')
const detail = ref('')

// (Re)seed the form whenever the modal opens, from the entry being edited or blank for a new one.
watch(
  () => props.open,
  (isOpen) => {
    if (!isOpen) return
    const e = props.entry
    kind.value = (e?.kind as typeof kind.value) || 'mcu'
    name.value = e?.name || ''
    boardId.value = e?.board_id ?? null
    connection.value = e?.connection || 'unknown'
    iface.value = e?.interface || ''
    displayKind.value = (e?.display_kind as typeof displayKind.value) || 'touch'
    detail.value = e?.detail || ''
  },
  { immediate: true },
)

const valid = computed(() => {
  if (kind.value === 'mcu') return name.value.trim().length > 0
  if (kind.value === 'canbus') return iface.value.trim().length > 0
  return name.value.trim().length > 0
})

const isEdit = computed(() => !!props.entry?.id)

function submit(): void {
  if (!valid.value) return
  const entry: ManualAddition = { kind: kind.value }
  if (props.entry?.id) entry.id = props.entry.id
  if (kind.value === 'mcu') {
    entry.name = name.value.trim()
    entry.board_id = boardId.value || null
    entry.connection = connection.value
  } else if (kind.value === 'canbus') {
    entry.interface = iface.value.trim()
    entry.board_id = boardId.value || null
  } else {
    entry.name = name.value.trim()
    entry.display_kind = displayKind.value
    entry.detail = detail.value.trim() || null
  }
  emit('submit', entry)
}

const CONN = ['usb', 'canbus', 'uart', 'unknown'] as const
const DKIND = ['touch', 'knomi', 'other'] as const
</script>

<template>
  <div
    v-if="open"
    class="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 p-3"
    role="dialog"
    aria-modal="true"
    @click.self="emit('close')"
  >
    <div class="nb-card w-full max-w-sm space-y-2 bg-surface p-3 text-sm">
      <div class="flex items-center justify-between gap-2">
        <h3 class="font-display text-sm font-bold">
          {{ isEdit ? t('boardTopology.manual.titleEdit') : t('boardTopology.manual.titleAdd') }}
        </h3>
        <button type="button" class="nb-btn bg-paper px-1.5 py-0.5" @click="emit('close')">
          ✕
        </button>
      </div>

      <!-- kind (locked while editing - the store keys by kind) -->
      <label class="block space-y-0.5">
        <span class="opacity-60">{{ t('boardTopology.manual.type') }}</span>
        <select v-model="kind" class="nb-input w-full bg-paper px-1 py-0.5" :disabled="isEdit">
          <option value="mcu">{{ t('boardTopology.manual.kindMcu') }}</option>
          <option value="canbus">{{ t('boardTopology.manual.kindCanbus') }}</option>
          <option value="display">{{ t('boardTopology.manual.kindDisplay') }}</option>
        </select>
      </label>

      <!-- MCU fields -->
      <template v-if="kind === 'mcu'">
        <label class="block space-y-0.5">
          <span class="opacity-60">{{ t('boardTopology.manual.mcuName') }}</span>
          <input
            v-model="name"
            type="text"
            dir="ltr"
            class="nb-input w-full bg-paper px-1 py-0.5"
            :placeholder="t('boardTopology.manual.mcuNamePlaceholder')"
          />
        </label>
        <label class="block space-y-0.5">
          <span class="opacity-60">{{ t('boardTopology.manual.connection') }}</span>
          <select v-model="connection" class="nb-input w-full bg-paper px-1 py-0.5">
            <option v-for="c in CONN" :key="c" :value="c">
              {{ t('boardTopology.conn.' + c) }}
            </option>
          </select>
        </label>
        <div class="space-y-0.5">
          <span class="opacity-60">{{ t('boardTopology.manual.board') }}</span>
          <HardwarePicker
            type="boards"
            :model-value="boardId"
            :placeholder="t('boardTopology.override.pickPlaceholder')"
            @update:model-value="(v) => (boardId = v)"
          />
        </div>
      </template>

      <!-- USB-CAN adapter fields -->
      <template v-else-if="kind === 'canbus'">
        <label class="block space-y-0.5">
          <span class="opacity-60">{{ t('boardTopology.manual.interface') }}</span>
          <input
            v-model="iface"
            type="text"
            dir="ltr"
            class="nb-input w-full bg-paper px-1 py-0.5"
            :placeholder="t('boardTopology.manual.interfacePlaceholder')"
          />
        </label>
        <div class="space-y-0.5">
          <span class="opacity-60">{{ t('boardTopology.manual.board') }}</span>
          <HardwarePicker
            type="boards"
            :model-value="boardId"
            :placeholder="t('boardTopology.override.pickPlaceholder')"
            @update:model-value="(v) => (boardId = v)"
          />
        </div>
      </template>

      <!-- Host display fields -->
      <template v-else>
        <label class="block space-y-0.5">
          <span class="opacity-60">{{ t('boardTopology.manual.displayKind') }}</span>
          <select v-model="displayKind" class="nb-input w-full bg-paper px-1 py-0.5">
            <option v-for="d in DKIND" :key="d" :value="d">
              {{ t('boardTopology.manual.d_' + d) }}
            </option>
          </select>
        </label>
        <label class="block space-y-0.5">
          <span class="opacity-60">{{ t('boardTopology.manual.displayName') }}</span>
          <input
            v-model="name"
            type="text"
            class="nb-input w-full bg-paper px-1 py-0.5"
            :placeholder="t('boardTopology.manual.displayNamePlaceholder')"
          />
        </label>
        <label class="block space-y-0.5">
          <span class="opacity-60">{{ t('boardTopology.manual.detail') }}</span>
          <input v-model="detail" type="text" class="nb-input w-full bg-paper px-1 py-0.5" />
        </label>
      </template>

      <div class="flex items-center justify-end gap-2 border-t border-ink/15 pt-2">
        <button type="button" class="nb-btn bg-paper px-2 py-0.5" @click="emit('close')">
          {{ t('boardTopology.manual.cancel') }}
        </button>
        <button
          type="button"
          class="nb-btn bg-brand-lime px-2 py-0.5 font-bold text-ink disabled:opacity-40"
          :disabled="!valid || busy"
          @click="submit"
        >
          {{ t('boardTopology.manual.save') }}
        </button>
      </div>
    </div>
  </div>
</template>
