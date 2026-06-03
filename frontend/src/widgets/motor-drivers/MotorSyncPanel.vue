<script setup lang="ts">
/** Motor synchronization (P8). Drives the optional motors_sync add-on to align the
 *  microstep phase of multiple motors on one axis (dual/quad-Z, dual-X). It's a separate
 *  Klipper add-on, so this checks whether it's installed; if so it offers a gated run /
 *  calibrate (accelerometer-based, moves the toolhead). Printer-level, shown once.
 */
import { onMounted, ref } from 'vue'

import { fetchMotorsSyncStatus, runMotorsSync } from './api'

const open = ref(false)
const available = ref<boolean | null>(null) // null = not checked yet
const confirmed = ref(false)
const busy = ref(false)
const msg = ref<string | null>(null)
const ok = ref(false)

onMounted(async () => {
  try {
    available.value = (await fetchMotorsSyncStatus()).available
  } catch {
    available.value = false
  }
})

async function run(calibrate: boolean): Promise<void> {
  busy.value = true
  msg.value = null
  try {
    const res = await runMotorsSync(calibrate)
    ok.value = res.ok
    msg.value = res.message
  } catch (e) {
    ok.value = false
    msg.value = e instanceof Error ? e.message : String(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="font-mono text-[10px]">
    <button
      class="opacity-60 transition-opacity hover:opacity-100"
      :aria-expanded="open"
      @click="open = !open"
    >
      {{ open ? '▾' : '🔗' }} motor synchronization
      <span v-if="available === false" class="opacity-50">(add-on not installed)</span>
    </button>

    <div
      v-if="open"
      class="mt-1 space-y-1.5 rounded-brutal border-2 border-dashed border-ink bg-paper p-2"
    >
      <p class="opacity-70">
        Aligns the microstep phase of multiple motors on one axis (dual / quad-Z, dual-X) using an
        accelerometer, so they don't fight each other. Provided by the separate
        <b>motors_sync</b> add-on.
      </p>

      <p v-if="available === null" class="opacity-60">checking…</p>

      <p v-else-if="!available" class="opacity-70">
        Not installed on this printer. Install the motors_sync add-on to enable it here.
      </p>

      <template v-else>
        <div class="rounded-brutal border-2 border-ink bg-brand-red px-1.5 py-1 text-surface">
          ⚠ This moves the toolhead for a while (it probes each motor). Keep clear and ready to cut
          power.
        </div>
        <label class="flex items-start gap-1.5">
          <input v-model="confirmed" type="checkbox" class="mt-0.5 shrink-0" />
          <span>I'm watching the printer — run motor synchronization now.</span>
        </label>
        <div class="flex flex-wrap gap-1.5">
          <button
            class="nb-btn bg-brand-yellow px-2 py-0.5 text-[10px]"
            :disabled="!confirmed || busy"
            @click="run(false)"
          >
            {{ busy ? '…' : 'sync motors' }}
          </button>
          <button
            class="nb-btn bg-surface px-2 py-0.5 text-[10px]"
            :disabled="!confirmed || busy"
            @click="run(true)"
          >
            calibrate
          </button>
        </div>
      </template>

      <p
        v-if="msg"
        class="rounded-brutal border-2 border-ink px-1.5 py-0.5"
        :class="ok ? 'bg-brand-lime' : 'bg-brand-red text-surface'"
      >
        {{ msg }}
      </p>
    </div>
  </div>
</template>
