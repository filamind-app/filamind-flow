<script setup lang="ts">
// The native touch home: a large-tile grid over the flow tools. Tile labels reuse the flow's
// existing per-widget translations (widgetTitle), so they are localized in every shipped locale.
import { widgetTitle } from '@/core/i18n'

const emit = defineEmits<{ open: [id: string] }>()

interface Tile {
  id: string
  title: string
  icon: string
}

// id + English title mirror the flow widget registry; widgetTitle resolves the localized label.
const tiles: Tile[] = [
  { id: 'machine-doctor', title: 'Machine Doctor', icon: '\u{1FA7A}' },
  { id: 'firmware-upgrade', title: 'Firmware Manager', icon: '\u{1F527}' },
  { id: 'input-shaping', title: 'Input Shaping', icon: '\u{1F4C8}' },
  { id: 'material-brain', title: 'Material Brain', icon: '\u{1F9E0}' },
  { id: 'tuning', title: 'Tuning Wizards', icon: '\u{1F39A}' },
  { id: 'preflight', title: 'Pre-Print Check', icon: '\u{1F6A6}' },
  { id: 'config-editor', title: 'Config Editor', icon: '\u{1F4DD}' },
  { id: 'motor-drivers', title: 'Motor Drivers', icon: '⚙' },
  { id: 'max-flow', title: 'Max-Flow', icon: '\u{1F321}' },
]
</script>

<template>
  <div class="grid">
    <button
      v-for="tl in tiles"
      :key="tl.id"
      class="tile"
      type="button"
      @click="emit('open', tl.id)"
    >
      <span class="ic" aria-hidden="true">{{ tl.icon }}</span>
      <span class="label">{{ widgetTitle(tl) }}</span>
    </button>
  </div>
</template>

<style scoped>
.grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
}
.tile {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  min-height: 110px;
  padding: 16px;
  background: var(--fm-surface, #17171c);
  border: 1px solid var(--fm-border, #3a3320);
  border-radius: 18px;
  color: var(--fm-text, #f3ecd8);
  cursor: pointer;
  transition:
    transform 0.08s ease,
    border-color 0.15s ease;
}
.tile:active {
  transform: scale(0.97);
}
.tile:hover {
  border-color: var(--fm-primary, #d4af37);
}
.tile .ic {
  font-size: 34px;
  line-height: 1;
}
.tile .label {
  font-size: 15px;
  font-weight: 500;
  text-align: center;
}
</style>
