<script setup lang="ts">
/** A terminal-style log pane (#113): the `bg-ink` box + per-line coloring (failures red,
 *  OK/complete green, `>>>` step lines cyan). Shared so every build / flash / op log renders
 *  identically instead of each panel re-implementing it.
 *
 *  With `reportable`, a small "⚐ Report" button appears whenever the log contains failure lines,
 *  letting the user open a pre-filled GitHub issue from those exact lines. */
import { computed } from 'vue'

import ReportErrorButton from '@/components/feedback/ReportErrorButton.vue'

const props = withDefaults(
  defineProps<{ log: string; maxClass?: string; reportable?: boolean }>(),
  { maxClass: 'max-h-48', reportable: false },
)

function lineClass(line: string): string {
  if (line.startsWith('!!') || /fail/i.test(line)) return 'text-brand-red'
  if (line.includes('=====') || /\bOK\b|complete|successful/i.test(line)) return 'text-brand-lime'
  if (line.startsWith('>>>')) return 'text-brand-cyan'
  return 'text-surface opacity-80'
}

// The failing lines, surfaced to the report button so the issue carries the relevant output.
const failingLines = computed(() =>
  props.reportable
    ? props.log
        .split('\n')
        .filter((l) => l.startsWith('!!') || /fail/i.test(l))
        .join('\n')
    : '',
)
</script>

<template>
  <div>
    <div v-if="reportable && failingLines" class="mb-1 flex justify-end">
      <ReportErrorButton :error="failingLines" />
    </div>
    <!-- role="log" so assistive tech treats appended lines as a live log, not noise. -->
    <div
      role="log"
      class="overflow-auto rounded-brutal border-2 border-ink bg-ink p-2 font-mono text-[11px] leading-tight"
      :class="maxClass"
    >
      <div
        v-for="(line, i) in log.split('\n')"
        :key="i"
        :class="['whitespace-pre-wrap break-all', lineClass(line)]"
      >
        {{ line }}
      </div>
    </div>
  </div>
</template>
