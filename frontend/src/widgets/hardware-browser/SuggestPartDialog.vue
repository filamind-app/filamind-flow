<script setup lang="ts">
/** "Suggest a part" — a per-category form that composes a catalog-shaped JSON fragment and opens a
 *  pre-filled GitHub issue for review (no token, never auto-posts). Field structure comes from
 *  contributeSchema; labels come from i18n (hardwareBrowser.suggest.*). Mirrors the report dialog:
 *  Teleport + backdrop + Escape, a form phase and a sent phase. */
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { openSubmission, submissionTooLong } from '@/core/contribute'

import {
  buildFragment,
  PART_TYPES,
  slugify,
  typeDef,
  type FieldDef,
  type PartType,
  type PortEntry,
} from './contributeSchema'

const props = defineProps<{ open: boolean; initialType: PartType; presetCategory?: string }>()
const emit = defineEmits<{ (e: 'close'): void }>()

const { t, te } = useI18n({ useScope: 'global' })
const tt = t as unknown as (key: string, named?: Record<string, unknown>) => string
const tte = te as unknown as (key: string) => boolean

const GROUP_ORDER = ['autotune', 'caps', 'maxFlow', 'preset'] as const

const type = ref<PartType>('motor')
const phase = ref<'form' | 'sent'>('form')
const values = reactive<Record<string, string | boolean>>({})
const specs = ref<{ key: string; value: string }[]>([])
const ports = ref<PortEntry[]>([])
const configSnippet = ref('')
const firstField = ref<HTMLElement | null>(null)
let lastFocused: HTMLElement | null = null

const def = computed(() => typeDef(type.value))
const topFields = computed(() => def.value.fields.filter((f) => !f.group || f.group === 'top'))
const groups = computed(() => {
  const out: { name: string; fields: FieldDef[] }[] = []
  for (const g of GROUP_ORDER) {
    const fields = def.value.fields.filter((f) => f.group === g)
    if (fields.length) out.push({ name: g, fields })
  }
  return out
})

function resetForm(): void {
  for (const k of Object.keys(values)) delete values[k]
  for (const f of def.value.fields) values[f.key] = f.type === 'checkbox' ? false : ''
  if (type.value === 'catalog' && props.presetCategory) values.category = props.presetCategory
  specs.value = []
  ports.value = []
  configSnippet.value = ''
  phase.value = 'form'
}

watch(
  () => props.open,
  (open) => {
    if (open) {
      lastFocused = (document.activeElement as HTMLElement) ?? null
      type.value = props.initialType
      resetForm()
      void nextTick(() => firstField.value?.focus())
      window.addEventListener('keydown', onKey)
    } else {
      window.removeEventListener('keydown', onKey)
      lastFocused?.focus?.()
      lastFocused = null
    }
  },
)
watch(type, resetForm)

function onKey(e: KeyboardEvent): void {
  if (e.key === 'Escape') emit('close')
}
// Guaranteed cleanup: the dialog lives inside an unmountable widget, so the open-watcher's
// remove-on-close won't run if the user navigates away while it's open.
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))

function labelFor(f: FieldDef): string {
  const key = `hardwareBrowser.suggest.f.${f.key}`
  const base = tte(key) ? tt(key) : f.key
  return f.unit ? `${base} (${f.unit})` : base
}
function groupLabel(name: string): string {
  const key = `hardwareBrowser.suggest.group.${name}`
  return tte(key) ? tt(key) : name
}

const slugPreview = computed(() => {
  if (!def.value.idKey) return ''
  const base =
    type.value === 'board'
      ? `${values.manufacturer ?? ''} ${values.model ?? ''}`
      : `${values.manufacturer ?? ''} ${values.name ?? ''}`
  return slugify(String(base))
})

const canSubmit = computed(() =>
  def.value.fields
    .filter((f) => f.required)
    .every((f) => String(values[f.key] ?? '').trim() !== ''),
)

const labelText = computed(() =>
  type.value === 'board'
    ? `${values.manufacturer ?? ''} ${values.model ?? ''}`.trim()
    : `${values.manufacturer ?? ''} ${values.name ?? ''}`.trim(),
)

const fragment = computed(() =>
  buildFragment(type.value, {
    values: { ...values },
    specs: specs.value,
    ports: ports.value,
    configSnippet: configSnippet.value,
  }),
)
const fragmentJson = computed(() => JSON.stringify(fragment.value, null, 2))

// A very large submission (e.g. a board with many ports) would overflow the GitHub prefill URL.
// Block submit and offer the JSON for a manual issue instead of opening a doomed tab.
const urlTooLong = computed(() =>
  submissionTooLong({ type: type.value, label: labelText.value, fragment: fragment.value }),
)
const copied = ref(false)
async function copyJson(): Promise<void> {
  try {
    await navigator.clipboard?.writeText(fragmentJson.value)
    copied.value = true
  } catch {
    // best-effort — the JSON is shown in the preview for manual copy when the clipboard is blocked
  }
}

function addSpec(): void {
  specs.value.push({ key: '', value: '' })
}
function addPort(): void {
  ports.value.push({ label: '', category: '', portFunction: '', pinMap: [] })
}
function addPin(p: PortEntry): void {
  p.pinMap.push({ signal: '', pin: '' })
}

function submit(): void {
  if (!canSubmit.value || urlTooLong.value) return
  if (openSubmission({ type: type.value, label: labelText.value, fragment: fragment.value })) {
    phase.value = 'sent'
  }
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="open"
      data-feedback-noshot
      class="fixed inset-0 z-[60] flex items-center justify-center p-4"
    >
      <div class="absolute inset-0 bg-ink/50" @click="emit('close')" />

      <div
        class="nb-card relative z-10 flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden bg-paper p-0"
        role="dialog"
        aria-modal="true"
        :aria-label="t('hardwareBrowser.suggest.title')"
      >
        <header
          class="flex items-center justify-between gap-2 border-b-3 border-ink bg-brand-cyan p-3"
        >
          <h2 class="font-display text-lg font-bold">
            <span aria-hidden="true">➕</span> {{ t('hardwareBrowser.suggest.title') }}
          </h2>
          <button
            class="nb-btn bg-surface px-2 py-1 text-xs"
            :aria-label="t('hardwareBrowser.suggest.cancel')"
            @click="emit('close')"
          >
            <span aria-hidden="true">✕</span>
          </button>
        </header>

        <!-- Form -->
        <div v-if="phase === 'form'" class="min-h-0 flex-1 space-y-3 overflow-y-auto p-3 text-sm">
          <p class="text-xs opacity-70">{{ t('hardwareBrowser.suggest.intro') }}</p>

          <!-- Type selector -->
          <label class="block space-y-1">
            <span class="text-xs font-bold">{{ t('hardwareBrowser.suggest.typeLabel') }}</span>
            <select
              ref="firstField"
              v-model="type"
              class="w-full rounded-brutal border-2 border-ink bg-surface p-2 text-sm"
            >
              <option v-for="p in PART_TYPES" :key="p.type" :value="p.type">
                {{ p.icon }} {{ t('hardwareBrowser.suggest.types.' + p.type) }}
              </option>
            </select>
          </label>

          <!-- Top fields -->
          <div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <label v-for="f in topFields" :key="f.key" class="block space-y-0.5">
              <span class="text-[11px] font-bold">
                {{ labelFor(f) }}<span v-if="f.required" class="text-brand-red"> *</span>
              </span>
              <select
                v-if="f.type === 'select'"
                v-model="values[f.key]"
                class="w-full rounded-brutal border-2 border-ink bg-surface p-1.5 text-xs"
              >
                <option value="">—</option>
                <option v-for="o in f.options" :key="o" :value="o">{{ o }}</option>
              </select>
              <label v-else-if="f.type === 'checkbox'" class="flex items-center gap-2 pt-1">
                <input v-model="values[f.key]" type="checkbox" class="h-4 w-4" />
                <span class="text-[11px] opacity-70">{{ t('hardwareBrowser.suggest.yes') }}</span>
              </label>
              <input
                v-else
                v-model="values[f.key]"
                :type="f.type === 'number' ? 'number' : 'text'"
                step="any"
                class="w-full rounded-brutal border-2 border-ink bg-surface p-1.5 text-xs"
              />
            </label>
          </div>

          <p v-if="slugPreview" class="font-mono text-[10px] opacity-50">id: {{ slugPreview }}</p>

          <!-- Grouped sub-objects (autotune / caps / maxFlow / preset) -->
          <fieldset
            v-for="g in groups"
            :key="g.name"
            class="rounded-brutal border-2 border-ink/40 p-2"
          >
            <legend class="px-1 text-[11px] font-bold opacity-70">{{ groupLabel(g.name) }}</legend>
            <div class="grid grid-cols-2 gap-2 sm:grid-cols-3">
              <label v-for="f in g.fields" :key="f.key" class="block space-y-0.5">
                <span class="text-[10px] opacity-70">{{ labelFor(f) }}</span>
                <select
                  v-if="f.type === 'select'"
                  v-model="values[f.key]"
                  class="w-full rounded-brutal border-2 border-ink bg-surface p-1 text-xs"
                >
                  <option value="">—</option>
                  <option v-for="o in f.options" :key="o" :value="o">{{ o }}</option>
                </select>
                <label v-else-if="f.type === 'checkbox'" class="flex items-center gap-1.5 pt-1">
                  <input v-model="values[f.key]" type="checkbox" class="h-4 w-4" />
                </label>
                <input
                  v-else
                  v-model="values[f.key]"
                  :type="f.type === 'number' ? 'number' : 'text'"
                  step="any"
                  class="w-full rounded-brutal border-2 border-ink bg-surface p-1 text-xs"
                />
              </label>
            </div>
          </fieldset>

          <!-- Ports (boards) -->
          <fieldset v-if="def.hasPorts" class="rounded-brutal border-2 border-ink/40 p-2">
            <legend class="px-1 text-[11px] font-bold opacity-70">
              {{ t('hardwareBrowser.suggest.ports') }}
            </legend>
            <div
              v-for="(p, pi) in ports"
              :key="pi"
              class="mb-2 rounded-brutal border border-ink/30 p-2"
            >
              <div class="grid grid-cols-3 gap-1.5">
                <input
                  v-model="p.label"
                  :placeholder="t('hardwareBrowser.suggest.f.portLabel')"
                  class="rounded-brutal border-2 border-ink bg-surface p-1 text-xs"
                />
                <input
                  v-model="p.category"
                  :placeholder="t('hardwareBrowser.suggest.f.portCategory')"
                  class="rounded-brutal border-2 border-ink bg-surface p-1 text-xs"
                />
                <input
                  v-model="p.portFunction"
                  :placeholder="t('hardwareBrowser.suggest.f.portFunction')"
                  class="rounded-brutal border-2 border-ink bg-surface p-1 text-xs"
                />
              </div>
              <div v-for="(m, mi) in p.pinMap" :key="mi" class="mt-1.5 grid grid-cols-2 gap-1.5">
                <input
                  v-model="m.signal"
                  :placeholder="t('hardwareBrowser.suggest.f.signal')"
                  class="rounded-brutal border-2 border-ink bg-surface p-1 font-mono text-xs"
                />
                <input
                  v-model="m.pin"
                  :placeholder="t('hardwareBrowser.suggest.f.pin')"
                  class="rounded-brutal border-2 border-ink bg-surface p-1 font-mono text-xs"
                />
              </div>
              <div class="mt-1.5 flex gap-2">
                <button class="nb-btn bg-surface px-2 py-0.5 text-[10px]" @click="addPin(p)">
                  + {{ t('hardwareBrowser.suggest.addPin') }}
                </button>
                <button
                  class="nb-btn bg-surface px-2 py-0.5 text-[10px]"
                  @click="ports.splice(pi, 1)"
                >
                  {{ t('hardwareBrowser.suggest.remove') }}
                </button>
              </div>
            </div>
            <button class="nb-btn bg-surface px-2 py-1 text-[11px]" @click="addPort">
              + {{ t('hardwareBrowser.suggest.addPort') }}
            </button>
          </fieldset>

          <!-- Free-form specs -->
          <fieldset v-if="def.hasSpecs" class="rounded-brutal border-2 border-ink/40 p-2">
            <legend class="px-1 text-[11px] font-bold opacity-70">
              {{ t('hardwareBrowser.suggest.specs') }}
            </legend>
            <div
              v-for="(s, si) in specs"
              :key="si"
              class="mb-1.5 grid grid-cols-[1fr_1fr_auto] gap-1.5"
            >
              <input
                v-model="s.key"
                :placeholder="t('hardwareBrowser.suggest.specKey')"
                class="rounded-brutal border-2 border-ink bg-surface p-1 text-xs"
              />
              <input
                v-model="s.value"
                :placeholder="t('hardwareBrowser.suggest.specValue')"
                class="rounded-brutal border-2 border-ink bg-surface p-1 text-xs"
              />
              <button class="nb-btn bg-surface px-2 text-[10px]" @click="specs.splice(si, 1)">
                ✕
              </button>
            </div>
            <button class="nb-btn bg-surface px-2 py-1 text-[11px]" @click="addSpec">
              + {{ t('hardwareBrowser.suggest.addSpec') }}
            </button>
          </fieldset>

          <!-- Config snippet -->
          <label v-if="def.hasConfig" class="block space-y-0.5">
            <span class="text-[11px] font-bold">{{
              t('hardwareBrowser.suggest.configSnippet')
            }}</span>
            <textarea
              v-model="configSnippet"
              rows="3"
              class="w-full rounded-brutal border-2 border-ink bg-surface p-2 font-mono text-[11px]"
            ></textarea>
          </label>

          <!-- JSON preview -->
          <details class="rounded-brutal border-2 border-ink bg-surface">
            <summary class="cursor-pointer px-2 py-1.5 text-xs font-bold">
              {{ t('hardwareBrowser.suggest.preview') }}
            </summary>
            <pre
              class="max-h-48 overflow-auto border-t-2 border-ink/20 bg-ink p-2 font-mono text-[10px] text-surface"
              >{{ fragmentJson }}</pre
            >
          </details>

          <p
            v-if="urlTooLong"
            class="nb-card flex flex-wrap items-center gap-2 bg-brand-yellow/20 p-2 text-[11px]"
          >
            <span class="min-w-0 flex-1">
              <span aria-hidden="true">⚠</span> {{ t('hardwareBrowser.suggest.tooLong') }}
            </span>
            <button class="nb-btn shrink-0 bg-surface px-2 py-0.5 text-[10px]" @click="copyJson">
              {{
                copied ? t('hardwareBrowser.suggest.copied') : t('hardwareBrowser.suggest.copyJson')
              }}
            </button>
          </p>

          <p class="text-[11px] opacity-60">{{ t('hardwareBrowser.suggest.languageNote') }}</p>
        </div>

        <!-- Sent -->
        <div v-else class="min-h-0 flex-1 space-y-3 overflow-y-auto p-3 text-sm">
          <p class="font-bold">
            <span aria-hidden="true">✅</span> {{ t('hardwareBrowser.suggest.sentTitle') }}
          </p>
          <p class="opacity-80">{{ t('hardwareBrowser.suggest.sentBody') }}</p>
        </div>

        <footer class="flex items-center justify-end gap-2 border-t-3 border-ink p-3">
          <template v-if="phase === 'form'">
            <button class="nb-btn bg-surface px-3 py-1.5 text-sm" @click="emit('close')">
              {{ t('hardwareBrowser.suggest.cancel') }}
            </button>
            <button
              class="nb-btn bg-brand-lime px-3 py-1.5 text-sm"
              :disabled="!canSubmit || urlTooLong"
              @click="submit"
            >
              <span aria-hidden="true">↗</span> {{ t('hardwareBrowser.suggest.submit') }}
            </button>
          </template>
          <button v-else class="nb-btn bg-brand-lime px-3 py-1.5 text-sm" @click="emit('close')">
            {{ t('hardwareBrowser.suggest.close') }}
          </button>
        </footer>
      </div>
    </div>
  </Teleport>
</template>
