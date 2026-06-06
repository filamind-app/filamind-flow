<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import HelpDrawer from '@/components/ui/HelpDrawer.vue'
import { describeError } from '@/core/describeError'

import { fetchTopology } from './api'
import HelpIllo from './HelpIllo.vue'
import { GLOSSARY_KEYS, HELP_ILLO, HELP_TOPICS } from './help'
import type { Topology } from './types'

const { t } = useI18n({ useScope: 'global' })

const topology = ref<Topology | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)

function connLabel(conn: string): string {
  switch (conn) {
    case 'canbus':
      return t('boardTopology.conn.canbus')
    case 'usb':
      return t('boardTopology.conn.usb')
    case 'uart':
      return t('boardTopology.conn.uart')
    default:
      return t('boardTopology.conn.unknown')
  }
}

function connClass(conn: string): string {
  switch (conn) {
    case 'canbus':
      return 'bg-brand-cyan text-ink'
    case 'usb':
      return 'bg-brand-lime text-ink'
    case 'uart':
      return 'bg-brand-yellow text-ink'
    default:
      return 'bg-paper text-ink'
  }
}

async function load(): Promise<void> {
  loading.value = true
  try {
    const data = await fetchTopology()
    topology.value = data
    error.value = data.reachable === false ? t('boardTopology.states.unreachable') : null
  } catch (e) {
    error.value = describeError(e)
    topology.value = null
  } finally {
    loading.value = false
  }
}

onMounted(() => void load())
</script>

<template>
  <div class="space-y-3 text-sm">
    <!-- Intro + help -->
    <div class="flex items-start justify-between gap-2">
      <p class="min-w-0 flex-1 text-xs opacity-70">{{ t('boardTopology.intro') }}</p>
      <div class="flex shrink-0 items-center gap-2">
        <HelpDrawer
          namespace="boardTopology"
          :topics="HELP_TOPICS"
          :illo-map="HELP_ILLO"
          :illo="HelpIllo"
          :glossary-keys="GLOSSARY_KEYS"
          steps-key="boardTopology.help.steps"
          :button-label="t('boardTopology.help.guide')"
          :title="t('boardTopology.help.guideTitle')"
          :close-label="t('boardTopology.help.close')"
          :steps-title="t('boardTopology.help.howToRead')"
        />
        <HelpIllo illo="host" class="h-8 w-8 opacity-70" />
      </div>
    </div>

    <div class="flex justify-end">
      <button class="nb-btn bg-surface px-2 py-1 text-xs" :disabled="loading" @click="load">
        <span aria-hidden="true">↻</span> {{ t('boardTopology.states.refresh') }}
      </button>
    </div>

    <!-- States -->
    <p v-if="loading && !topology" class="font-mono text-xs opacity-70">
      {{ t('boardTopology.states.loading') }}
    </p>
    <div v-else-if="error" class="nb-card space-y-2 bg-brand-red/10 p-2">
      <p class="font-mono text-xs">{{ error }}</p>
      <p v-if="topology?.detail" class="font-mono text-[11px] opacity-70">{{ topology.detail }}</p>
      <button class="nb-btn bg-surface px-2 py-1 text-xs" @click="load">
        {{ t('boardTopology.states.retry') }}
      </button>
    </div>
    <p v-else-if="topology && !topology.mcus.length" class="font-mono text-xs opacity-70">
      {{ t('boardTopology.states.empty') }}
    </p>

    <!-- Topology -->
    <template v-if="topology && !error && topology.mcus.length">
      <!-- Host -->
      <div class="flex flex-col items-center gap-1">
        <div class="nb-card bg-brand-yellow px-3 py-2 text-center">
          <div class="font-display font-bold">
            <span aria-hidden="true">🖥</span> {{ t('boardTopology.host.label') }}
          </div>
          <div class="text-[10px] opacity-70">{{ t('boardTopology.host.role') }}</div>
        </div>
        <div class="h-4 w-0.5 bg-ink" aria-hidden="true"></div>
        <div class="text-[10px] opacity-60">
          {{ t('boardTopology.count', { n: topology.mcu_count }) }}
        </div>
      </div>

      <!-- MCU cards -->
      <ul class="grid gap-2 sm:grid-cols-2">
        <li v-for="(m, i) in topology.mcus" :key="i" class="nb-card space-y-1 bg-surface p-2">
          <div class="flex items-center justify-between gap-2">
            <span class="min-w-0 truncate font-mono text-xs font-bold">{{ m.name }}</span>
            <span
              class="shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold"
              :class="connClass(m.connection)"
            >
              {{ connLabel(m.connection) }}
            </span>
          </div>
          <div class="font-mono text-[11px]">
            <span class="opacity-60">{{ t('boardTopology.mcu.chip') }}:</span>
            {{ m.mcu || t('boardTopology.mcu.unknown') }}
          </div>
          <div v-if="m.board" class="font-mono text-[11px]">
            <span class="opacity-60">{{ t('boardTopology.mcu.board') }}:</span> {{ m.board }}
            <span v-if="m.confidence > 0" class="opacity-50">
              ({{ t('boardTopology.mcu.confidence', { pct: Math.round(m.confidence * 100) }) }})
            </span>
          </div>
          <div
            v-if="m.identifier"
            class="truncate font-mono text-[10px] opacity-50"
            :title="m.identifier"
          >
            {{ m.identifier }}
          </div>
        </li>
      </ul>
    </template>
  </div>
</template>
