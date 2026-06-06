<script setup lang="ts">
/** A collapsible "ℹ what's this?" note for the Firmware Upgrade widget. Collapsed by
 *  default so it adds zero clutter; expands a dashed teaching block (copy from the i18n
 *  catalog + an illustration). The `glossary` topic renders the term list (after its body).
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { GLOSSARY_KEYS, HELP_ILLO, type HelpTopic } from './help'
import HelpIllo from './HelpIllo.vue'

const props = defineProps<{ topic: HelpTopic }>()
const { t, te } = useI18n({ useScope: 'global' })
// Keys are built from the (typed) topic at runtime; the schema-typed t/te only accept literal
// keys, so use string-accepting views (the runtime resolves dynamic keys fine).
const tt = t as unknown as (key: string) => string
const tte = te as unknown as (key: string) => boolean

const open = ref(false)
const illo = HELP_ILLO[props.topic]
const title = computed(() => tt(`firmware.help.topics.${props.topic}.title`))
const bodyKey = computed(() => `firmware.help.topics.${props.topic}.body`)
const hasBody = computed(() => tte(bodyKey.value))
</script>

<template>
  <div class="font-mono text-[10px]">
    <button
      class="opacity-60 transition-opacity hover:opacity-100"
      :aria-expanded="open"
      @click="open = !open"
    >
      <span aria-hidden="true">{{ open ? '▾' : 'ℹ' }}</span> {{ title }}
    </button>
    <div
      v-if="open"
      class="mt-1 flex items-start gap-2 rounded-brutal border-2 border-dashed border-ink bg-paper p-2"
    >
      <HelpIllo v-if="illo" :illo="illo" class="mt-0.5 h-10 w-10 shrink-0 opacity-80" />
      <div class="min-w-0 flex-1 space-y-1 leading-snug opacity-80">
        <p v-if="hasBody">{{ tt(bodyKey) }}</p>
        <dl v-if="topic === 'glossary'" class="space-y-1">
          <div v-for="k in GLOSSARY_KEYS" :key="k">
            <dt class="font-bold">{{ tt(`firmware.help.glossary.${k}.term`) }}</dt>
            <dd>{{ tt(`firmware.help.glossary.${k}.def`) }}</dd>
          </div>
        </dl>
      </div>
    </div>
  </div>
</template>
