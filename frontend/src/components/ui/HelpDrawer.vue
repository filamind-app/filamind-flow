<script setup lang="ts">
/** A shared, off-canvas "guide" drawer — one organised home for a widget's help, instead of a
 *  scattered row of identical "what's this?" links. A single labelled button opens it; the drawer
 *  lists an optional "how to read" step list, every help topic (title + illustration + body), and
 *  the glossary. All copy comes from the widget's i18n namespace; the per-widget illustration
 *  component is injected via the `illo` prop so this component stays generic.
 *
 *  Mirrors the app sidebar's off-canvas pattern (backdrop + end-anchored panel) so it feels native
 *  and flips correctly under RTL. Closes on backdrop click, the ✕ button, or Escape.
 */
import { onBeforeUnmount, ref, watch, type Component } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps<{
  /** i18n namespace, e.g. 'motorDrivers' — topic/glossary keys are built from it. */
  namespace: string
  /** Help topics in display order (the glossary topic is rendered separately at the end). */
  topics: readonly string[]
  /** topic -> illustration key (passed straight to the injected `illo` component). */
  illoMap: Partial<Record<string, string>>
  /** The widget's HelpIllo component (kept generic — each widget has its own art). */
  illo: Component
  /** Glossary term keys in display order. */
  glossaryKeys: readonly string[]
  /** Optional ordered "how to read" steps (an i18n array message key, rendered via `tm`). */
  stepsKey?: string
  /** Translated chrome (the parent owns these strings). */
  buttonLabel: string
  title: string
  closeLabel: string
  stepsTitle?: string
}>()

const { t, te, tm, rt } = useI18n({ useScope: 'global' })
// Topic/glossary keys are built at runtime; the schema-typed t/te only accept literal keys.
const tt = t as unknown as (key: string) => string
const tte = te as unknown as (key: string) => boolean
// `tm()` over a dynamic key returns raw message nodes; `rt()` resolves each to a string.
const rtt = rt as unknown as (msg: unknown) => string
const steps = (): unknown[] => (props.stepsKey ? (tm(props.stepsKey) as unknown[]) : [])

const open = ref(false)
const GLOSSARY = 'glossary'

function topicTitle(topic: string): string {
  return tt(`${props.namespace}.help.topics.${topic}.title`)
}
function topicBodyKey(topic: string): string {
  return `${props.namespace}.help.topics.${topic}.body`
}

function close(): void {
  open.value = false
}
function onKey(e: KeyboardEvent): void {
  if (e.key === 'Escape') close()
}
watch(open, (isOpen) => {
  if (isOpen) window.addEventListener('keydown', onKey)
  else window.removeEventListener('keydown', onKey)
})
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <button class="nb-btn bg-surface px-2 py-1 text-xs" :aria-expanded="open" @click="open = true">
    <span aria-hidden="true">❓</span> {{ buttonLabel }}
  </button>

  <Teleport to="body">
    <div v-if="open">
      <!-- Backdrop -->
      <div class="fixed inset-0 z-40 bg-ink/50" @click="close" />

      <!-- Panel: anchored to the inline-end, flips with dir -->
      <aside
        class="fixed inset-y-0 end-0 z-50 flex w-full max-w-md flex-col border-s-3 border-ink bg-paper shadow-brutal-lg"
        role="dialog"
        aria-modal="true"
        :aria-label="title"
      >
        <header
          class="flex items-center justify-between gap-2 border-b-3 border-ink bg-brand-cyan p-3"
        >
          <h2 class="font-display text-lg font-bold">{{ title }}</h2>
          <button class="nb-btn bg-surface px-2 py-1 text-xs" @click="close">
            <span aria-hidden="true">✕</span> {{ closeLabel }}
          </button>
        </header>

        <div class="min-h-0 flex-1 space-y-4 overflow-y-auto p-3 text-sm leading-snug">
          <!-- How to read (optional ordered steps) -->
          <section v-if="stepsKey">
            <h3 class="mb-1 font-display text-base font-bold">{{ stepsTitle }}</h3>
            <ol class="list-decimal space-y-1 ps-5 opacity-90">
              <li v-for="(s, i) in steps()" :key="i">{{ rtt(s) }}</li>
            </ol>
          </section>

          <!-- Topics (each: title + illustration + body) -->
          <section
            v-for="topic in topics.filter((x) => x !== GLOSSARY)"
            :key="topic"
            class="nb-card bg-surface p-2"
          >
            <div class="flex items-start gap-2">
              <component
                :is="illo"
                v-if="illoMap[topic]"
                :illo="illoMap[topic]"
                class="mt-0.5 h-9 w-9 shrink-0 opacity-80"
              />
              <div class="min-w-0 flex-1 space-y-1">
                <h3 class="font-bold">{{ topicTitle(topic) }}</h3>
                <p v-if="tte(topicBodyKey(topic))" class="opacity-80">
                  {{ tt(topicBodyKey(topic)) }}
                </p>
              </div>
            </div>
          </section>

          <!-- Glossary -->
          <section v-if="glossaryKeys.length" class="nb-card bg-surface p-2">
            <h3 class="mb-1 font-bold">{{ topicTitle(GLOSSARY) }}</h3>
            <dl class="space-y-1.5">
              <div v-for="k in glossaryKeys" :key="k">
                <dt class="font-bold">{{ tt(`${namespace}.help.glossary.${k}.term`) }}</dt>
                <dd class="opacity-80">{{ tt(`${namespace}.help.glossary.${k}.def`) }}</dd>
              </div>
            </dl>
          </section>
        </div>
      </aside>
    </div>
  </Teleport>
</template>
