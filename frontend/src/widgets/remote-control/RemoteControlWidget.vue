<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import HelpDrawer from '@/components/ui/HelpDrawer.vue'
import { useRemoteControlStore } from '@/core/store/remoteControl'
import type { RemoteMessageLevel } from '@/core/remote/commands'

import RemoteControlHelpIllo from './RemoteControlHelpIllo.vue'

const { t } = useI18n()
const store = useRemoteControlStore()

const messageText = ref('')
const level = ref<RemoteMessageLevel>('info')
const flash = ref(false) // brief "Sent" confirmation
let flashTimer: ReturnType<typeof setTimeout> | undefined

const views = computed(() => [
  { view: 'status' as const, label: t('remoteControl.show.status') },
  { view: 'control' as const, label: t('remoteControl.show.control') },
  { view: 'settings' as const, label: t('remoteControl.show.settings') },
])
const levels = computed(() => [
  { value: 'info' as const, label: t('remoteControl.message.info') },
  { value: 'warn' as const, label: t('remoteControl.message.warn') },
])

function markSent(): void {
  flash.value = true
  if (flashTimer) clearTimeout(flashTimer)
  flashTimer = setTimeout(() => (flash.value = false), 2000)
}

async function nav(view: 'status' | 'control' | 'settings'): Promise<void> {
  await store.navigate(view)
  markSent()
}
async function locate(): Promise<void> {
  await store.locate()
  markSent()
}
async function sendMessage(): Promise<void> {
  const text = messageText.value.trim()
  if (!text) return
  await store.message(level.value, text)
  messageText.value = ''
  markSent()
}

onMounted(() => store.init())
onUnmounted(() => {
  if (flashTimer) clearTimeout(flashTimer)
})
</script>

<template>
  <div class="flex flex-col gap-4">
    <header class="flex items-center justify-between gap-3">
      <p class="text-sm text-ink/70">{{ t('remoteControl.intro') }}</p>
      <div class="flex shrink-0 items-center gap-2">
        <span
          class="nb-badge text-xs"
          :class="store.ready ? 'bg-brand-green' : 'bg-surface text-ink/70'"
          role="status"
        >
          {{ store.ready ? t('remoteControl.status.ready') : t('remoteControl.status.down') }}
        </span>
        <HelpDrawer
          namespace="remoteControl"
          :topics="['overview', 'commands']"
          :illo-map="{}"
          :illo="RemoteControlHelpIllo"
          :glossary-keys="[]"
          :button-label="t('remoteControl.help.button')"
          :title="t('remoteControl.help.title')"
          :close-label="t('remoteControl.help.close')"
        />
      </div>
    </header>

    <p v-if="flash" class="nb-card bg-brand-green/30 p-2 text-sm" role="status">
      {{ t('remoteControl.sent') }}
    </p>

    <section class="nb-card flex flex-col gap-2 p-3">
      <h3 class="font-display text-sm font-bold uppercase tracking-wide text-ink/60">
        {{ t('remoteControl.show.title') }}
      </h3>
      <div class="flex flex-wrap gap-2">
        <button
          v-for="v in views"
          :key="v.view"
          class="nb-btn px-3 py-1.5"
          :disabled="!store.ready"
          @click="nav(v.view)"
        >
          {{ v.label }}
        </button>
      </div>
    </section>

    <section class="nb-card flex flex-col gap-2 p-3">
      <h3 class="font-display text-sm font-bold uppercase tracking-wide text-ink/60">
        {{ t('remoteControl.locate.title') }}
      </h3>
      <p class="text-sm text-ink/70">{{ t('remoteControl.locate.hint') }}</p>
      <button class="nb-btn w-fit px-3 py-1.5" :disabled="!store.ready" @click="locate">
        📍 {{ t('remoteControl.locate.button') }}
      </button>
    </section>

    <section class="nb-card flex flex-col gap-2 p-3">
      <h3 class="font-display text-sm font-bold uppercase tracking-wide text-ink/60">
        {{ t('remoteControl.message.title') }}
      </h3>
      <textarea
        v-model="messageText"
        class="nb-input min-h-16 w-full p-2 text-sm"
        :aria-label="t('remoteControl.message.title')"
        :placeholder="t('remoteControl.message.placeholder')"
        maxlength="280"
      ></textarea>
      <div class="flex flex-wrap items-center gap-2">
        <label class="text-sm text-ink/70" for="rc-level">{{
          t('remoteControl.message.level')
        }}</label>
        <select id="rc-level" v-model="level" class="nb-input px-2 py-1 text-sm">
          <option v-for="l in levels" :key="l.value" :value="l.value">{{ l.label }}</option>
        </select>
        <button
          class="nb-btn ms-auto px-3 py-1.5"
          :disabled="!store.ready || messageText.trim().length === 0"
          @click="sendMessage"
        >
          {{ t('remoteControl.message.send') }}
        </button>
      </div>
    </section>
  </div>
</template>
