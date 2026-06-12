<script setup lang="ts">
/** Language picker menu — a popover listing every available locale in its own native name and
 *  direction (Arabic shown RTL even from an LTR UI), with the active one marked. Renders nothing
 *  until more than one locale catalog exists. Esc or clicking outside closes. */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { availableLocales, setLocale } from '@/core/i18n'

const { t, locale } = useI18n({ useScope: 'global' })

const open = ref(false)
const root = ref<HTMLElement | null>(null)

const activeLabel = computed(
  () => availableLocales.find((m) => m.code === locale.value)?.label ?? String(locale.value),
)

function pick(code: string): void {
  void setLocale(code)
  open.value = false
}

function onDocClick(event: MouseEvent): void {
  if (open.value && root.value && !root.value.contains(event.target as Node)) open.value = false
}
function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') open.value = false
}
onMounted(() => {
  document.addEventListener('click', onDocClick)
  document.addEventListener('keydown', onKeydown)
})
onUnmounted(() => {
  document.removeEventListener('click', onDocClick)
  document.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <div v-if="availableLocales.length > 1" ref="root" class="relative">
    <button
      class="nb-btn px-2.5 py-1.5 text-sm"
      :aria-label="t('shell.language.menu')"
      :aria-expanded="open"
      aria-haspopup="true"
      :title="t('shell.language.menu')"
      @click="open = !open"
    >
      <span aria-hidden="true">🌐</span>
      <span class="hidden lg:inline">{{ activeLabel }}</span>
    </button>

    <div
      v-if="open"
      class="nb-card absolute end-0 top-full z-50 mt-2 w-48 p-1.5"
      role="menu"
      :aria-label="t('shell.language.menu')"
    >
      <p class="mb-1 px-1.5 text-xs font-bold opacity-70">{{ t('shell.language.menu') }}</p>
      <button
        v-for="m in availableLocales"
        :key="m.code"
        role="menuitemradio"
        :aria-checked="locale === m.code"
        :lang="m.code"
        :dir="m.dir"
        class="flex w-full items-center justify-between gap-2 rounded-brutal px-2 py-1.5 text-start text-sm hover:bg-ink/10"
        :class="{ 'font-bold': locale === m.code }"
        @click="pick(m.code)"
      >
        <span>{{ m.label }}</span>
        <span v-if="locale === m.code" aria-hidden="true">✓</span>
      </button>
    </div>
  </div>
</template>
