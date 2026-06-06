<script setup lang="ts">
/** A typeahead combobox (dropdown) for long option lists (#120). One control that opens a
 *  filtered dropdown with keyboard navigation (↑/↓/Enter/Esc), instead of an always-open inline
 *  list. Shared UI primitive — the convention for every long picker (motors today, filaments /
 *  boards / profiles tomorrow). Generic over `{ value, label, sublabel }` options. The dropdown
 *  shows the WHOLE list (scrollable) so a user who doesn't remember the name can browse (#130).
 */
import { computed, nextTick, ref, watch } from 'vue'

interface ComboOption {
  value: string
  label: string
  sublabel?: string
}

const props = withDefaults(
  defineProps<{
    modelValue: string | null
    options: ComboOption[]
    placeholder?: string
    disabled?: boolean
    clearable?: boolean
  }>(),
  { placeholder: 'Select…', disabled: false, clearable: false },
)
const emit = defineEmits<{ 'update:modelValue': [value: string | null] }>()

// Unique per-instance id prefix so multiple comboboxes on one page don't collide on option ids.
let comboSeq = 0
const uid = `combo-${(comboSeq += 1)}`

const root = ref<HTMLElement | null>(null)
const input = ref<HTMLInputElement | null>(null)
const list = ref<HTMLElement | null>(null)
const open = ref(false)
const query = ref('')
const activeIndex = ref(0)

const selected = computed(() => props.options.find((o) => o.value === props.modelValue) ?? null)

function matches(o: ComboOption, q: string): boolean {
  return o.label.toLowerCase().includes(q) || (o.sublabel ?? '').toLowerCase().includes(q)
}
// The full filtered list — no cap, so the whole catalog is browsable (the dropdown scrolls).
const shown = computed(() => {
  const q = query.value.trim().toLowerCase()
  return q ? props.options.filter((o) => matches(o, q)) : props.options
})

function openMenu(): void {
  if (props.disabled) return
  open.value = true
  query.value = ''
  activeIndex.value = 0
  void nextTick(() => input.value?.focus())
}
function close(): void {
  open.value = false
}
function select(value: string | null): void {
  emit('update:modelValue', value)
  close()
}
function scrollActiveIntoView(): void {
  void nextTick(() => {
    const el = list.value?.children[activeIndex.value] as HTMLElement | undefined
    el?.scrollIntoView({ block: 'nearest' })
  })
}
function onFocusOut(e: FocusEvent): void {
  // Close only when focus leaves the whole control (option clicks keep focus inside root).
  if (!root.value?.contains(e.relatedTarget as Node | null)) close()
}
function onKeydown(e: KeyboardEvent): void {
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    activeIndex.value = Math.min(activeIndex.value + 1, shown.value.length - 1)
    scrollActiveIntoView()
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    activeIndex.value = Math.max(activeIndex.value - 1, 0)
    scrollActiveIntoView()
  } else if (e.key === 'Enter') {
    e.preventDefault()
    const opt = shown.value[activeIndex.value]
    if (opt) select(opt.value)
  } else if (e.key === 'Escape') {
    close()
  }
}
watch(query, () => (activeIndex.value = 0))
</script>

<template>
  <div ref="root" class="relative font-mono text-[11px]" @focusout="onFocusOut">
    <button
      type="button"
      class="flex w-full items-center justify-between gap-1 rounded-brutal border-2 border-ink bg-surface px-1.5 py-1 text-start"
      :disabled="disabled"
      role="combobox"
      aria-haspopup="listbox"
      :aria-expanded="open"
      @click="open ? close() : openMenu()"
    >
      <span class="min-w-0 truncate" :class="{ 'opacity-50': !selected }">
        {{ selected ? selected.label : placeholder }}
      </span>
      <span class="shrink-0 opacity-60">{{ open ? '▴' : '▾' }}</span>
    </button>

    <div
      v-if="open"
      class="absolute z-30 mt-1 w-full space-y-1 rounded-brutal border-2 border-ink bg-paper p-1 shadow-brutal-sm"
    >
      <input
        ref="input"
        v-model="query"
        type="text"
        :placeholder="placeholder"
        :aria-label="placeholder"
        class="w-full rounded-brutal border-2 border-ink bg-surface px-1.5 py-1"
        :aria-activedescendant="shown[activeIndex] ? `${uid}-opt-${activeIndex}` : undefined"
        @keydown="onKeydown"
      />
      <button
        v-if="clearable && modelValue"
        type="button"
        class="block w-full px-1 py-0.5 text-start text-brand-red hover:underline"
        @click="select(null)"
      >
        ✕ clear
      </button>
      <ul ref="list" role="listbox" aria-label="Options" class="max-h-72 overflow-y-auto">
        <li v-for="(o, i) in shown" :key="o.value">
          <button
            :id="`${uid}-opt-${i}`"
            type="button"
            role="option"
            :aria-selected="o.value === modelValue"
            class="w-full rounded px-1 py-0.5 text-start hover:bg-surface"
            :class="{ 'bg-surface': i === activeIndex }"
            @click="select(o.value)"
            @mousemove="activeIndex = i"
          >
            <b>{{ o.label }}</b>
            <span v-if="o.sublabel" class="opacity-60"> {{ o.sublabel }}</span>
          </button>
        </li>
        <li v-if="!shown.length" class="px-1 py-0.5 opacity-60">no matches</li>
      </ul>
      <div class="px-1 opacity-50">{{ shown.length }} shown</div>
    </div>
  </div>
</template>
