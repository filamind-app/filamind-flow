<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useSessionStore } from '../core/store/session'
import DashboardView from '../views/DashboardView.vue'

interface Heater {
  temperature?: number
  target?: number
}
interface PrintStats {
  state?: string
}

// Glyphs kept as ASCII escapes in source (the template binds them) so the file stays ASCII-clean.
const icons = {
  logo: '\u{1F525}',
  hotend: '\u{1F321}',
  bed: '\u{1F6CF}',
}

const { t, te } = useI18n()
const store = useSessionStore()

const ext = computed(() => store.object<Heater>('extruder'))
const bed = computed(() => store.object<Heater>('heater_bed'))
const stats = computed<PrintStats>(() => store.object<PrintStats>('print_stats') ?? {})
const state = computed(() => stats.value.state ?? 'standby')

const stateLabel = computed(() => {
  const key = `touch.state.${state.value}`
  return te(key) ? t(key) : state.value
})
const stateKind = computed(() => {
  if (!store.live) return 'offline'
  if (state.value === 'printing') return 'printing'
  if (state.value === 'paused') return 'paused'
  return 'idle'
})

function fmt(n?: number): string {
  return n == null ? '-' : `${Math.round(n)}°`
}

// Tiles tap through to a per-tool touch view; until each lands, surface a brief notice.
const toast = ref('')
let toastTimer: ReturnType<typeof setTimeout> | undefined
function comingSoon(): void {
  toast.value = t('touch.comingSoon')
  if (toastTimer) clearTimeout(toastTimer)
  toastTimer = setTimeout(() => (toast.value = ''), 1600)
}
</script>

<template>
  <div class="shell">
    <header class="bar top">
      <div class="brand">
        <span class="logo" aria-hidden="true">{{ icons.logo }}</span>
        <span class="name">FilaMind Flow</span>
        <span class="sub">{{ t('touch.subtitle') }}</span>
      </div>
      <div class="status">
        <span class="temp">
          <span class="ic" aria-hidden="true">{{ icons.hotend }}</span>
          {{ fmt(ext?.temperature) }} / {{ fmt(ext?.target) }}
        </span>
        <span class="temp">
          <span class="ic" aria-hidden="true">{{ icons.bed }}</span>
          {{ fmt(bed?.temperature) }} / {{ fmt(bed?.target) }}
        </span>
        <span class="pill" :class="stateKind">{{ stateLabel }}</span>
      </div>
    </header>

    <main class="body">
      <DashboardView @open="comingSoon" />
    </main>

    <transition name="fade">
      <div v-if="toast" class="toast">{{ toast }}</div>
    </transition>
  </div>
</template>

<style scoped>
.shell {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 18px;
}
.top {
  border-bottom: 1px solid var(--fm-border, #3a3320);
}
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
}
.logo {
  font-size: 22px;
}
.name {
  font-size: 18px;
  font-weight: 600;
}
.sub {
  font-size: 12px;
  color: var(--fm-text-muted, #9a917c);
}
.status {
  display: flex;
  align-items: center;
  gap: 16px;
}
.temp {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-variant-numeric: tabular-nums;
  font-size: 15px;
  white-space: nowrap;
}
.temp .ic {
  opacity: 0.7;
}
.pill {
  font-size: 13px;
  padding: 4px 12px;
  border-radius: 999px;
  background: var(--fm-surface-2, #20202a);
  border: 1px solid var(--fm-border, #3a3320);
}
.pill.printing {
  color: var(--fm-success, #2ba199);
}
.pill.paused {
  color: var(--fm-warning, #e0a92e);
}
.pill.offline {
  color: var(--fm-danger, #9e2b25);
}
.body {
  flex: 1;
  overflow: auto;
  padding: 16px;
}
.toast {
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  background: var(--fm-surface-2, #20202a);
  color: var(--fm-text, #f3ecd8);
  border: 1px solid var(--fm-border, #3a3320);
  padding: 10px 18px;
  border-radius: 999px;
  font-size: 14px;
}
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
