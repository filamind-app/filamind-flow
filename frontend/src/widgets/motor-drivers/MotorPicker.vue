<script setup lang="ts">
/** Per-stepper motor picker: shows the assigned motor (+ specs) and, when opened, a
 *  searchable list of the catalogued motors. Emits `assign` (stepper, model | null);
 *  the parent persists it and refreshes. Pure list logic lives in `format.ts`.
 */
import { computed, ref } from 'vue'

import { filterMotors, motorSpecLabel } from './format'
import type { MotorSpec } from './types'

const props = defineProps<{
  stepper: string
  assigned: MotorSpec | null
  catalog: MotorSpec[]
  defaultOpen?: boolean
}>()
const emit = defineEmits<{ assign: [stepper: string, model: string | null] }>()

const open = ref(props.defaultOpen === true)
const query = ref('')

//: Cap the rendered list — 200+ rows at once is needless DOM; refine via search.
const LIMIT = 60
const matches = computed(() => filterMotors(props.catalog, query.value))
const shown = computed(() => matches.value.slice(0, LIMIT))

function pick(model: string | null): void {
  emit('assign', props.stepper, model)
  open.value = false
  query.value = ''
}
</script>

<template>
  <div class="font-mono text-[10px]">
    <div class="flex items-center justify-between gap-2">
      <span class="min-w-0 truncate">
        <span class="opacity-60">motor:</span>
        <b v-if="assigned">{{ assigned.manufacturer }} {{ assigned.model }}</b>
        <span v-else class="opacity-60">not set</span>
      </span>
      <button
        class="shrink-0 opacity-60 transition-opacity hover:opacity-100"
        :aria-expanded="open"
        @click="open = !open"
      >
        {{ open ? 'close' : assigned ? 'change' : '+ pick motor' }}
      </button>
    </div>
    <div v-if="assigned" class="truncate opacity-70">{{ motorSpecLabel(assigned) }}</div>

    <div
      v-if="open"
      class="mt-1 space-y-1 rounded-brutal border-2 border-dashed border-ink bg-paper p-2"
    >
      <input
        v-model="query"
        type="text"
        placeholder="search 200+ motors (model or maker)…"
        class="w-full rounded-brutal border-2 border-ink bg-surface px-1.5 py-0.5 text-[10px]"
      />
      <button v-if="assigned" class="text-brand-red hover:underline" @click="pick(null)">
        ✕ clear assignment
      </button>
      <ul class="max-h-44 space-y-0.5 overflow-y-auto">
        <li v-for="m in shown" :key="`${m.manufacturer}::${m.model}`">
          <button
            class="w-full rounded px-1 py-0.5 text-left hover:bg-surface"
            @click="pick(m.model)"
          >
            <b>{{ m.model }}</b>
            <span class="opacity-60"> {{ m.manufacturer }} · {{ motorSpecLabel(m) }}</span>
          </button>
        </li>
        <li v-if="!shown.length" class="opacity-60">no matches</li>
      </ul>
      <div v-if="matches.length > shown.length" class="opacity-50">
        showing {{ shown.length }} of {{ matches.length }} — refine your search
      </div>
    </div>
  </div>
</template>
