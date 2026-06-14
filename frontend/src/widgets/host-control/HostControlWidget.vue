<script setup lang="ts">
/** Host Control — manage the printer host's Linux OS.
 *
 *  Phase 1: a read-only health + OS-state monitor (CPU / temp / memory / disk / network / time /
 *  locale + top processes), auto-refreshing while visible. Services, disk cleanup and the
 *  system-changing actions (time / locale / hostname / power) build on this in later phases. */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import HelpDrawer from '@/components/ui/HelpDrawer.vue'
import { describeError } from '@/core/describeError'

import { fetchMonitor } from './api'
import CleanupPanel from './CleanupPanel.vue'
import { GLOSSARY_KEYS, HELP_ILLO, HELP_TOPICS } from './help'
import HelpIllo from './HelpIllo.vue'
import ServicesPanel from './ServicesPanel.vue'
import SystemPanel from './SystemPanel.vue'
import type { HostMonitor } from './types'

const { t } = useI18n({ useScope: 'global' })

type View = 'monitor' | 'services' | 'cleanup' | 'system'
const view = ref<View>('monitor')

const monitor = ref<HostMonitor | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)
const autoRefresh = ref(true)
let timer: ReturnType<typeof setInterval> | null = null

const REFRESH_MS = 5000

async function load(): Promise<void> {
  // Only the first load shows the full spinner; auto-refresh updates in place.
  if (!monitor.value) loading.value = true
  error.value = null
  try {
    monitor.value = await fetchMonitor()
  } catch (e) {
    error.value = describeError(e)
  } finally {
    loading.value = false
  }
}

function startAuto(): void {
  if (timer) return
  timer = setInterval(() => {
    if (autoRefresh.value && view.value === 'monitor') void load()
  }, REFRESH_MS)
}

function stopAuto(): void {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}

onMounted(() => {
  void load()
  startAuto()
})
onUnmounted(stopAuto)

// ── formatters ───────────────────────────────────────────────────────────────
function fmtUptime(s: number | null): string {
  if (s == null) return '—'
  const d = Math.floor(s / 86400)
  const h = Math.floor((s % 86400) / 3600)
  const m = Math.floor((s % 3600) / 60)
  const parts: string[] = []
  if (d) parts.push(`${d}d`)
  if (h || d) parts.push(`${h}h`)
  parts.push(`${m}m`)
  return parts.join(' ')
}

function fmtSize(bytes: number): string {
  if (bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let v = bytes
  let i = 0
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024
    i += 1
  }
  return `${v.toFixed(v >= 100 || i === 0 ? 0 : 1)} ${units[i]}`
}

const fmtKb = (kb: number): string => fmtSize(kb * 1024)

const memPct = computed(() => {
  const m = monitor.value?.memory
  if (!m || !m.total_kb) return 0
  return Math.round((m.used_kb / m.total_kb) * 100)
})

const swapPct = computed(() => {
  const m = monitor.value?.memory
  if (!m || !m.swap_total_kb) return 0
  return Math.round((m.swap_used_kb / m.swap_total_kb) * 100)
})

/** Colour a usage bar: amber past 75%, red past 90%. */
function barClass(pct: number): string {
  if (pct >= 90) return 'bg-brand-red'
  if (pct >= 75) return 'bg-brand-yellow'
  return 'bg-brand-cyan'
}

function tempClass(c: number | null): string {
  if (c == null) return ''
  if (c >= 80) return 'text-brand-red'
  if (c >= 70) return 'text-brand-yellow'
  return ''
}

/** Wi-Fi signal level (/proc/net/wireless link quality) → a short label. */
function signalLabel(sig: number | null): string {
  if (sig == null) return '—'
  return `${sig}`
}
</script>

<template>
  <div class="space-y-3 text-sm">
    <div class="flex items-start justify-between gap-2">
      <p class="min-w-0 flex-1 text-xs opacity-70">{{ t('hostControl.intro') }}</p>
      <HelpDrawer
        class="shrink-0"
        namespace="hostControl"
        :topics="HELP_TOPICS"
        :illo-map="HELP_ILLO"
        :illo="HelpIllo"
        :glossary-keys="GLOSSARY_KEYS"
        steps-key="hostControl.help.steps"
        :button-label="t('hostControl.help.guide')"
        :title="t('hostControl.help.guideTitle')"
        :close-label="t('hostControl.help.close')"
        :steps-title="t('hostControl.help.howToRead')"
      />
    </div>

    <!-- Monitor / Services view toggle -->
    <div class="-mx-1 overflow-x-auto px-1">
      <div class="inline-flex overflow-hidden rounded-brutal border-2 border-ink" role="group">
        <button
          v-for="v in ['monitor', 'services', 'cleanup', 'system'] as View[]"
          :key="v"
          type="button"
          class="nb-seg whitespace-nowrap"
          :class="view === v ? 'bg-ink text-surface' : 'bg-surface text-ink hover:bg-brand-cyan'"
          :aria-pressed="view === v"
          @click="view = v"
        >
          {{ t('hostControl.view.' + v) }}
        </button>
      </div>
    </div>

    <template v-if="view === 'monitor'">
      <!-- Toolbar -->
      <div class="flex flex-wrap items-center gap-2">
        <button type="button" class="nb-btn text-xs" :disabled="loading" @click="load">
          ↻ {{ t('hostControl.monitor.refresh') }}
        </button>
        <label class="flex cursor-pointer items-center gap-1.5 font-mono text-[11px] opacity-80">
          <input v-model="autoRefresh" type="checkbox" class="accent-ink" />
          {{ t('hostControl.monitor.autoRefresh') }}
        </label>
        <span v-if="loading && !monitor" class="font-mono text-[11px] opacity-60">
          {{ t('hostControl.monitor.loading') }}
        </span>
      </div>

      <p v-if="error" role="alert" class="nb-card bg-brand-red/10 p-2 font-mono text-xs">
        {{ error }}
      </p>

      <template v-if="monitor">
        <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <!-- Host -->
          <section class="nb-card space-y-1.5 bg-surface p-3">
            <h3 class="text-xs font-bold uppercase tracking-wide opacity-60">
              {{ t('hostControl.monitor.host') }}
            </h3>
            <dl class="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 font-mono text-[11px]">
              <dt class="opacity-60">{{ t('hostControl.monitor.hostname') }}</dt>
              <dd class="font-bold">{{ monitor.host.hostname || '—' }}</dd>
              <dt class="opacity-60">{{ t('hostControl.monitor.distro') }}</dt>
              <dd>{{ monitor.host.distro || '—' }}</dd>
              <dt class="opacity-60">{{ t('hostControl.monitor.kernel') }}</dt>
              <dd>{{ monitor.host.kernel || '—' }} ({{ monitor.host.arch }})</dd>
              <dt class="opacity-60">{{ t('hostControl.monitor.uptime') }}</dt>
              <dd>{{ fmtUptime(monitor.host.uptime_s) }}</dd>
            </dl>
          </section>

          <!-- CPU -->
          <section class="nb-card space-y-1.5 bg-surface p-3">
            <h3 class="text-xs font-bold uppercase tracking-wide opacity-60">
              {{ t('hostControl.monitor.cpu') }}
            </h3>
            <dl class="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 font-mono text-[11px]">
              <dt class="opacity-60">{{ t('hostControl.monitor.temp') }}</dt>
              <dd class="font-bold" :class="tempClass(monitor.cpu.temp_c)">
                {{ monitor.cpu.temp_c != null ? monitor.cpu.temp_c + ' °C' : '—' }}
              </dd>
              <dt class="opacity-60">{{ t('hostControl.monitor.load') }}</dt>
              <dd>{{ monitor.cpu.load ? monitor.cpu.load.join(' · ') : '—' }}</dd>
              <dt class="opacity-60">{{ t('hostControl.monitor.cores') }}</dt>
              <dd>{{ monitor.cpu.cores ?? '—' }}</dd>
            </dl>
            <p
              v-if="monitor.throttle.supported && monitor.throttle.flags.length"
              class="text-[11px] font-bold text-brand-red"
            >
              ⚠ {{ t('hostControl.monitor.throttled') }}: {{ monitor.throttle.flags.join(', ') }}
            </p>
          </section>

          <!-- Memory -->
          <section class="nb-card space-y-1.5 bg-surface p-3">
            <h3 class="text-xs font-bold uppercase tracking-wide opacity-60">
              {{ t('hostControl.monitor.memory') }}
            </h3>
            <div class="space-y-0.5">
              <div class="flex justify-between font-mono text-[11px]">
                <span class="opacity-60">{{ t('hostControl.monitor.ram') }}</span>
                <span
                  >{{ fmtKb(monitor.memory.used_kb) }} / {{ fmtKb(monitor.memory.total_kb) }} ({{
                    memPct
                  }}%)</span
                >
              </div>
              <div class="h-2 w-full overflow-hidden rounded-full border border-ink bg-paper">
                <div class="h-full" :class="barClass(memPct)" :style="{ width: memPct + '%' }" />
              </div>
            </div>
            <div v-if="monitor.memory.swap_total_kb" class="space-y-0.5">
              <div class="flex justify-between font-mono text-[11px]">
                <span class="opacity-60">{{ t('hostControl.monitor.swap') }}</span>
                <span
                  >{{ fmtKb(monitor.memory.swap_used_kb) }} /
                  {{ fmtKb(monitor.memory.swap_total_kb) }} ({{ swapPct }}%)</span
                >
              </div>
              <div class="h-2 w-full overflow-hidden rounded-full border border-ink bg-paper">
                <div class="h-full" :class="barClass(swapPct)" :style="{ width: swapPct + '%' }" />
              </div>
            </div>
          </section>

          <!-- Disk -->
          <section class="nb-card space-y-1.5 bg-surface p-3">
            <h3 class="text-xs font-bold uppercase tracking-wide opacity-60">
              {{ t('hostControl.monitor.disk') }}
            </h3>
            <div v-for="d in monitor.disk" :key="d.path" class="space-y-0.5">
              <div class="flex justify-between font-mono text-[11px]">
                <span class="opacity-60">{{ d.label }}</span>
                <span>{{ fmtSize(d.used) }} / {{ fmtSize(d.total) }} ({{ d.pct }}%)</span>
              </div>
              <div class="h-2 w-full overflow-hidden rounded-full border border-ink bg-paper">
                <div class="h-full" :class="barClass(d.pct)" :style="{ width: d.pct + '%' }" />
              </div>
            </div>
          </section>

          <!-- Network -->
          <section class="nb-card space-y-1.5 bg-surface p-3">
            <h3 class="text-xs font-bold uppercase tracking-wide opacity-60">
              {{ t('hostControl.monitor.network') }}
            </h3>
            <dl class="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 font-mono text-[11px]">
              <dt class="opacity-60">{{ t('hostControl.monitor.iface') }}</dt>
              <dd class="font-bold">{{ monitor.network.iface || '—' }}</dd>
              <dt class="opacity-60">{{ t('hostControl.monitor.ip') }}</dt>
              <dd>{{ monitor.network.ip || '—' }}</dd>
              <template v-if="monitor.network.ssid">
                <dt class="opacity-60">{{ t('hostControl.monitor.ssid') }}</dt>
                <dd>{{ monitor.network.ssid }}</dd>
                <dt class="opacity-60">{{ t('hostControl.monitor.signal') }}</dt>
                <dd>{{ signalLabel(monitor.network.signal) }}</dd>
              </template>
            </dl>
          </section>

          <!-- Time & Locale -->
          <section class="nb-card space-y-1.5 bg-surface p-3">
            <h3 class="text-xs font-bold uppercase tracking-wide opacity-60">
              {{ t('hostControl.monitor.timeLocale') }}
            </h3>
            <dl class="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 font-mono text-[11px]">
              <dt class="opacity-60">{{ t('hostControl.monitor.timezone') }}</dt>
              <dd class="font-bold">{{ monitor.time.timezone || '—' }}</dd>
              <dt class="opacity-60">{{ t('hostControl.monitor.ntp') }}</dt>
              <dd>
                <span v-if="monitor.time.ntp_synced" class="text-brand-green"
                  >✓ {{ t('hostControl.monitor.synced') }}</span
                >
                <span v-else-if="monitor.time.ntp_enabled" class="text-brand-yellow"
                  >⟳ {{ t('hostControl.monitor.syncing') }}</span
                >
                <span v-else class="opacity-70">{{ t('hostControl.monitor.ntpOff') }}</span>
              </dd>
              <dt class="opacity-60">{{ t('hostControl.monitor.language') }}</dt>
              <dd>{{ monitor.locale.lang || '—' }}</dd>
              <dt v-if="monitor.locale.keymap" class="opacity-60">
                {{ t('hostControl.monitor.keymap') }}
              </dt>
              <dd v-if="monitor.locale.keymap">{{ monitor.locale.keymap }}</dd>
            </dl>
          </section>
        </div>

        <!-- Top processes -->
        <section v-if="monitor.processes.length" class="nb-card space-y-1.5 bg-surface p-3">
          <h3 class="text-xs font-bold uppercase tracking-wide opacity-60">
            {{ t('hostControl.monitor.topProcesses') }}
          </h3>
          <table class="w-full font-mono text-[11px]">
            <thead class="opacity-60">
              <tr class="text-left">
                <th class="font-normal">{{ t('hostControl.monitor.command') }}</th>
                <th class="w-12 text-right font-normal">{{ t('hostControl.monitor.cpuPct') }}</th>
                <th class="w-12 text-right font-normal">{{ t('hostControl.monitor.memPct') }}</th>
                <th class="w-16 text-right font-normal">{{ t('hostControl.monitor.pid') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="p in monitor.processes" :key="p.pid" class="border-t border-ink/10">
                <td class="truncate">{{ p.command }}</td>
                <td class="text-right">{{ p.cpu.toFixed(1) }}</td>
                <td class="text-right">{{ p.mem.toFixed(1) }}</td>
                <td class="text-right opacity-60">{{ p.pid }}</td>
              </tr>
            </tbody>
          </table>
        </section>
      </template>
    </template>

    <ServicesPanel v-else-if="view === 'services'" />

    <CleanupPanel v-else-if="view === 'cleanup'" />

    <SystemPanel v-else-if="view === 'system'" />
  </div>
</template>
