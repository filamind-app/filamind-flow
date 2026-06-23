<script setup lang="ts">
/** Control - the real printer-control screen: the live print job, temperatures with quick
 *  material presets, motion (jog / home / Z babystep), and the webcam. Reads the shared printer
 *  store; every actuation goes straight to Moonraker and is gated by the printer guard (motion and
 *  temperature are refused mid-print; pause/resume/cancel stay available while a job runs). */
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import HelpDrawer from '@/components/ui/HelpDrawer.vue'
import { moonraker } from '@/core/moonraker'
import { usePrinterGuard } from '@/core/printerGuard'
import { usePrinterStore } from '@/core/store/printer'

import HelpIllo from './HelpIllo.vue'
import { GLOSSARY_KEYS, HELP_ILLO, HELP_TOPICS } from './help'

const { t } = useI18n({ useScope: 'global' })
const printer = usePrinterStore()
const guard = usePrinterGuard()

interface Heater {
  temperature?: number
  target?: number
}
interface PrintStats {
  state?: string
  filename?: string
  print_duration?: number
  info?: { current_layer?: number | null; total_layer?: number | null }
}
const obj = <T,>(name: string): T | undefined => printer.status[name] as T | undefined

const ext = computed(() => obj<Heater>('extruder'))
const bed = computed(() => obj<Heater>('heater_bed'))
const stats = computed<PrintStats>(() => obj<PrintStats>('print_stats') ?? {})
const sdProg = computed(() => obj<{ progress?: number }>('virtual_sdcard')?.progress)
const dispProg = computed(() => obj<{ progress?: number }>('display_status')?.progress)

const progress = computed(() => Math.round((sdProg.value ?? dispProg.value ?? 0) * 100))
const layer = computed(() => stats.value.info ?? {})
const state = computed(() => stats.value.state ?? 'standby')
const isPrinting = computed(() => state.value === 'printing')
const isPaused = computed(() => state.value === 'paused')
const active = computed(() => isPrinting.value || isPaused.value)
// Literal keys only (the schema-typed t rejects a runtime-built key).
const stateLabel = computed(() =>
  isPaused.value
    ? t('control.paused')
    : isPrinting.value
      ? t('control.printing')
      : t('control.job'),
)

const eta = computed(() => {
  const frac = sdProg.value ?? dispProg.value ?? 0
  const elapsed = stats.value.print_duration ?? 0
  if (!active.value || frac <= 0.01 || elapsed <= 0) return ''
  const m = Math.round((elapsed * (1 - frac)) / frac / 60)
  return m < 60 ? `${m}m` : `${Math.floor(m / 60)}h ${m % 60}m`
})
const fmt = (n?: number): string => `${Math.round(n ?? 0)}°`

// Motion / temperature are refused mid-print or while another op holds the slot; the buttons dim.
const motionBlocked = computed(() => guard.writesBlocked)
const busy = ref(false)
async function send(fn: () => Promise<unknown>): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    await fn()
  } catch {
    /* surfaced by the connection state; keep the panel resilient */
  } finally {
    busy.value = false
  }
}
const gcode = (script: string) => send(() => moonraker.call('printer.gcode.script', { script }))
const pause = () => send(() => moonraker.call('printer.print.pause'))
const resume = () => send(() => moonraker.call('printer.print.resume'))
const cancel = () => send(() => moonraker.call('printer.print.cancel'))
const home = () => gcode('G28')
function jog(axis: 'X' | 'Y' | 'Z', dist: number): void {
  void gcode(`G91\nG1 ${axis}${dist} F${axis === 'Z' ? 600 : 3000}\nG90`)
}
const babystep = (d: number) => gcode(`SET_GCODE_OFFSET Z_ADJUST=${d} MOVE=1`)

// temperatures: rolling sparkline + one-tap presets
const history = ref<number[]>([])
const extTemp = computed(() => ext.value?.temperature ?? 0)
watch(extTemp, (v) => (history.value = [...history.value.slice(-23), v]))
const spark = computed(() => {
  const xs = history.value.length ? history.value : [extTemp.value]
  const max = Math.max(60, ...xs)
  return xs
    .map(
      (v, i) =>
        `${xs.length > 1 ? (i / (xs.length - 1)) * 200 : 0},${(30 - (v / max) * 28).toFixed(1)}`,
    )
    .join(' ')
})
const presets = [
  { name: 'PLA', ext: 210, bed: 60 },
  { name: 'PETG', ext: 240, bed: 80 },
  { name: 'ABS', ext: 250, bed: 100 },
]
const activePreset = computed(
  () => presets.find((p) => p.ext === Math.round(ext.value?.target ?? -1))?.name,
)
const applyPreset = (p: (typeof presets)[number]) => gcode(`M104 S${p.ext}\nM140 S${p.bed}`)
const zOffset = computed(
  () => obj<{ homing_origin?: number[] }>('gcode_move')?.homing_origin?.[2] ?? 0,
)

const camOk = ref(true)
// Bound (not a literal src) so the bundler doesn't try to resolve the stream URL at build time.
const camUrl = '/webcam/?action=stream'
</script>

<template>
  <div class="mx-auto max-w-4xl">
    <div class="mb-3 flex items-center justify-between gap-2">
      <h2 class="font-display text-2xl font-bold">{{ t('control.title') }}</h2>
      <HelpDrawer
        namespace="control"
        :topics="HELP_TOPICS"
        :illo-map="HELP_ILLO"
        :illo="HelpIllo"
        :glossary-keys="GLOSSARY_KEYS"
        :button-label="t('control.help.guide')"
        :title="t('control.help.guideTitle')"
        :close-label="t('control.help.close')"
      />
    </div>
    <div class="grid gap-3 sm:grid-cols-2">
      <!-- Print job -->
      <section class="nb-card space-y-2 bg-surface p-3">
        <div class="flex items-center justify-between text-xs">
          <span class="font-bold uppercase tracking-wide opacity-60">{{ stateLabel }}</span>
          <span v-if="eta" class="opacity-60">{{ t('control.eta') }} {{ eta }}</span>
        </div>
        <template v-if="active">
          <p class="truncate font-mono text-xs">{{ stats.filename || '—' }}</p>
          <div class="h-2 w-full overflow-hidden rounded-full border border-ink bg-paper">
            <div class="h-full bg-brand-cyan" :style="{ width: progress + '%' }"></div>
          </div>
          <div class="flex justify-between font-mono text-[11px]">
            <span v-if="layer.total_layer" class="opacity-70"
              >{{ t('control.layer') }} {{ layer.current_layer ?? 0 }} /
              {{ layer.total_layer }}</span
            >
            <span class="font-bold">{{ progress }}%</span>
          </div>
          <div class="flex gap-2 pt-1">
            <button
              v-if="isPrinting"
              class="nb-btn bg-brand-yellow px-3 py-1 text-xs"
              @click="pause"
            >
              ⏸ {{ t('control.pause') }}
            </button>
            <button v-if="isPaused" class="nb-btn bg-brand-lime px-3 py-1 text-xs" @click="resume">
              ▶ {{ t('control.resume') }}
            </button>
            <button class="nb-btn bg-surface px-3 py-1 text-xs" @click="cancel">
              ⏹ {{ t('control.cancel') }}
            </button>
          </div>
        </template>
        <p v-else class="py-5 text-center text-xs opacity-60">{{ t('control.noJob') }}</p>
      </section>

      <!-- Temperatures -->
      <section class="nb-card space-y-2 bg-surface p-3">
        <p class="text-xs font-bold uppercase tracking-wide opacity-60">{{ t('control.temps') }}</p>
        <div class="flex gap-4 font-mono text-sm">
          <span
            >🔥 {{ fmt(ext?.temperature)
            }}<span class="opacity-60">/{{ fmt(ext?.target) }}</span></span
          >
          <span
            >🛏 {{ fmt(bed?.temperature)
            }}<span class="opacity-60">/{{ fmt(bed?.target) }}</span></span
          >
        </div>
        <svg viewBox="0 0 200 32" preserveAspectRatio="none" class="h-8 w-full">
          <polyline
            :points="spark"
            fill="none"
            stroke="currentColor"
            stroke-width="1.5"
            class="text-brand-cyan"
          />
        </svg>
        <div class="flex gap-2">
          <button
            v-for="p in presets"
            :key="p.name"
            class="nb-btn px-2.5 py-0.5 text-[11px]"
            :class="activePreset === p.name ? 'bg-brand-cyan' : 'bg-surface'"
            :disabled="motionBlocked"
            :title="`${p.ext}° / ${p.bed}°`"
            @click="applyPreset(p)"
          >
            {{ p.name }}
          </button>
        </div>
      </section>

      <!-- Motion -->
      <section class="nb-card space-y-2 bg-surface p-3">
        <p class="text-xs font-bold uppercase tracking-wide opacity-60">
          {{ t('control.motion') }}
        </p>
        <div class="flex items-center gap-4">
          <div class="motion-pad">
            <button
              class="nb-btn jog"
              style="grid-area: up"
              :disabled="motionBlocked"
              @click="jog('Y', 10)"
            >
              ▲
            </button>
            <button
              class="nb-btn jog"
              style="grid-area: left"
              :disabled="motionBlocked"
              @click="jog('X', -10)"
            >
              ◀
            </button>
            <button
              class="nb-btn jog bg-brand-lime"
              style="grid-area: home"
              :disabled="motionBlocked"
              :title="t('control.home')"
              @click="home"
            >
              ⌂
            </button>
            <button
              class="nb-btn jog"
              style="grid-area: right"
              :disabled="motionBlocked"
              @click="jog('X', 10)"
            >
              ▶
            </button>
            <button
              class="nb-btn jog"
              style="grid-area: down"
              :disabled="motionBlocked"
              @click="jog('Y', -10)"
            >
              ▼
            </button>
          </div>
          <div class="space-y-2">
            <div class="flex gap-1.5">
              <button
                class="nb-btn px-2 py-1 text-xs"
                :disabled="motionBlocked"
                @click="jog('Z', 1)"
              >
                Z▲
              </button>
              <button
                class="nb-btn px-2 py-1 text-xs"
                :disabled="motionBlocked"
                @click="jog('Z', -1)"
              >
                Z▼
              </button>
            </div>
            <div class="text-[11px] opacity-70">{{ t('control.babystep') }}</div>
            <div class="flex items-center gap-1.5">
              <button
                class="nb-btn px-2 py-0.5 text-[11px]"
                :disabled="motionBlocked"
                @click="babystep(-0.02)"
              >
                −0.02
              </button>
              <b class="w-12 text-center font-mono text-xs">{{ zOffset.toFixed(2) }}</b>
              <button
                class="nb-btn px-2 py-0.5 text-[11px]"
                :disabled="motionBlocked"
                @click="babystep(0.02)"
              >
                +0.02
              </button>
            </div>
          </div>
        </div>
      </section>

      <!-- Webcam -->
      <section class="nb-card space-y-2 bg-surface p-3">
        <div class="flex items-center justify-between text-xs">
          <span class="font-bold uppercase tracking-wide opacity-60">{{
            t('control.webcam')
          }}</span>
          <span v-if="camOk" class="text-brand-red">● {{ t('control.live') }}</span>
        </div>
        <div
          class="flex aspect-video items-center justify-center overflow-hidden rounded-brutal border border-ink bg-paper"
        >
          <img
            v-if="camOk"
            :src="camUrl"
            alt=""
            class="h-full w-full object-cover"
            @error="camOk = false"
          />
          <span v-else class="text-3xl opacity-30">🎥</span>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.motion-pad {
  display: grid;
  grid-template-columns: repeat(3, 2.2rem);
  grid-auto-rows: 2.2rem;
  gap: 0.3rem;
  grid-template-areas:
    '. up .'
    'left home right'
    '. down .';
}
.jog {
  padding: 0;
  min-height: 2.2rem;
  font-size: 0.85rem;
}
</style>
