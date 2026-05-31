<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import { fetchFlashPlan, fetchProfiles, flashBoard } from './api'
import type { Board, FirmwareProfile, FlashPlan, FlashRequest } from './types'

const props = defineProps<{ board: Board }>()
defineEmits<{ close: [] }>()

const profiles = ref<FirmwareProfile[]>([])
const selectedProfile = ref<string | null>(null)
const plan = ref<FlashPlan | null>(null)
const confirmed = ref(false)
const flashing = ref(false)
const flashLog = ref('')
const error = ref<string | null>(null)

const _CONNECTION_METHOD: Record<string, string> = {
  usb: 'serial',
  can: 'can',
  dfu: 'dfu',
  linux: 'linux',
}

const method = computed(() => {
  const profile = profiles.value.find((p) => p.name === selectedProfile.value)
  if (profile?.is_avr) return 'make'
  return _CONNECTION_METHOD[props.board.connection] ?? 'serial'
})

function request(): FlashRequest {
  return {
    profile: selectedProfile.value,
    method: method.value,
    device: props.board.id,
    interface: props.board.interface ?? 'can0',
  }
}

async function loadPlan(): Promise<void> {
  plan.value = null
  confirmed.value = false
  if (!selectedProfile.value) return
  error.value = null
  try {
    plan.value = await fetchFlashPlan(request())
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Could not load flash plan'
  }
}

async function doFlash(): Promise<void> {
  if (!plan.value?.ready || !confirmed.value || flashing.value) return
  flashing.value = true
  flashLog.value = `>>> flashing ${props.board.name}…\n`
  try {
    await flashBoard(request(), (chunk) => {
      flashLog.value += chunk
    })
  } catch (e) {
    flashLog.value += `\n!! ${e instanceof Error ? e.message : 'flash failed'}\n`
  } finally {
    flashing.value = false
  }
}

watch(selectedProfile, loadPlan)

onMounted(async () => {
  const all = (await fetchProfiles().catch(() => null))?.profiles ?? []
  profiles.value = all.filter((p) => p.built)
})
</script>

<template>
  <div class="space-y-2 text-sm">
    <div class="flex items-center justify-between gap-2">
      <span class="text-xs font-bold uppercase tracking-wide">Flash · {{ board.name }}</span>
      <button class="nb-btn px-2 py-0.5 text-xs" @click="$emit('close')">← back</button>
    </div>

    <div class="rounded-brutal border-2 border-ink p-2 text-xs">
      <span class="font-mono opacity-70">{{ board.connection }} · {{ board.id }}</span>
    </div>

    <select
      v-model="selectedProfile"
      class="w-full rounded-brutal border-2 border-ink bg-surface px-2 py-1 text-xs"
    >
      <option :value="null">— choose a built profile —</option>
      <option v-for="p in profiles" :key="p.name" :value="p.name">{{ p.name }}</option>
    </select>
    <p v-if="!profiles.length" class="font-mono text-[10px] opacity-60">
      No built profiles. Configure &amp; build one first.
    </p>

    <div v-if="error" class="nb-badge bg-brand-red text-surface">{{ error }}</div>

    <div v-if="plan" class="space-y-1.5 rounded-brutal border-2 border-ink p-2">
      <div class="flex items-center justify-between">
        <span class="font-bold">{{ plan.method }} → {{ plan.artifact ?? '—' }}</span>
        <span class="nb-badge" :class="plan.ready ? 'bg-brand-lime' : 'bg-brand-yellow'">
          {{ plan.ready ? 'ready' : 'blocked' }}
        </span>
      </div>
      <pre
        class="overflow-x-auto rounded-brutal border-2 border-ink bg-ink p-1.5 font-mono text-[10px] text-surface"
        >{{ plan.command }}</pre
      >
      <p v-for="w in plan.warnings" :key="w" class="font-mono text-[10px] text-brand-red">
        ⚠ {{ w }}
      </p>

      <label v-if="plan.ready" class="flex items-center gap-2 pt-1 text-[11px]">
        <input v-model="confirmed" type="checkbox" />
        I understand this writes firmware to <b>{{ board.name }}</b
        >.
      </label>
      <button
        class="nb-btn w-full bg-brand-red py-1 text-xs text-surface"
        :disabled="!plan.ready || !confirmed || flashing"
        @click="doFlash"
      >
        {{ flashing ? 'flashing…' : '⚠ Flash now' }}
      </button>
    </div>

    <pre
      v-if="flashLog"
      class="max-h-48 overflow-auto rounded-brutal border-2 border-ink bg-ink p-2 font-mono text-[10px] leading-tight text-surface"
      >{{ flashLog }}</pre
    >
  </div>
</template>
