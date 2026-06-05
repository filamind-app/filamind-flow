<script setup lang="ts">
/** A terminal-style log pane (#113): the `bg-ink` box + per-line coloring (failures red,
 *  OK/complete green, `>>>` step lines cyan). Shared so every build / flash / op log renders
 *  identically instead of each panel re-implementing it. */
withDefaults(defineProps<{ log: string; maxClass?: string }>(), { maxClass: 'max-h-48' })

function lineClass(line: string): string {
  if (line.startsWith('!!') || /fail/i.test(line)) return 'text-brand-red'
  if (line.includes('=====') || /\bOK\b|complete|successful/i.test(line)) return 'text-brand-lime'
  if (line.startsWith('>>>')) return 'text-brand-cyan'
  return 'text-surface opacity-80'
}
</script>

<template>
  <div
    class="overflow-auto rounded-brutal border-2 border-ink bg-ink p-2 font-mono text-[10px] leading-tight"
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
</template>
