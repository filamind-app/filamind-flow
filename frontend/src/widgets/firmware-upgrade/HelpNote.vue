<script setup lang="ts">
/** A collapsible "ℹ what's this?" note for the Firmware Upgrade widget. Collapsed by
 *  default so it adds zero clutter; expands a dashed teaching block (copy from help.ts +
 *  an illustration). The `glossary` topic renders the term list instead of a single body.
 */
import { ref } from 'vue'

import HelpIllo from './HelpIllo.vue'
import { GLOSSARY, HELP, type HelpTopic } from './help'

const props = defineProps<{ topic: HelpTopic }>()
const open = ref(false)
const entry = HELP[props.topic]
</script>

<template>
  <div class="font-mono text-[10px]">
    <button
      class="opacity-60 transition-opacity hover:opacity-100"
      :aria-expanded="open"
      @click="open = !open"
    >
      {{ open ? '▾' : 'ℹ' }} {{ open ? entry.title : "what's this?" }}
    </button>
    <div
      v-if="open"
      class="mt-1 flex items-start gap-2 rounded-brutal border-2 border-dashed border-ink bg-paper p-2"
    >
      <HelpIllo v-if="entry.illo" :illo="entry.illo" class="mt-0.5 h-10 w-10 shrink-0 opacity-80" />
      <div class="min-w-0 flex-1 space-y-1 leading-snug opacity-80">
        <p v-if="entry.body">{{ entry.body }}</p>
        <dl v-if="topic === 'glossary'" class="space-y-1">
          <div v-for="t in GLOSSARY" :key="t.term">
            <dt class="font-bold">{{ t.term }}</dt>
            <dd>{{ t.def }}</dd>
          </div>
        </dl>
      </div>
    </div>
  </div>
</template>
