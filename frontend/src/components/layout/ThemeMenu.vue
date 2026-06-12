<script setup lang="ts">
/** Theme picker menu — a popover of preview cards, one per theme.
 *
 *  Each card is a miniature of that theme (its own paper/surface/ink + accent dots, from the
 *  static swatch in THEME_META — NOT the live CSS vars, so every card shows what *that* theme
 *  would look like). Clicking applies + persists instantly; the active card is marked. Esc or
 *  clicking outside closes. */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { availableThemes, currentTheme, setTheme, type ThemeKey } from '@/core/theme'

const { t } = useI18n({ useScope: 'global' })

const open = ref(false)
const root = ref<HTMLElement | null>(null)

const activeLabel = computed(() => {
  const meta = availableThemes.find((m) => m.key === currentTheme.value)
  return meta ? t(meta.labelKey) : currentTheme.value
})

function pick(key: ThemeKey): void {
  setTheme(key)
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
  <div ref="root" class="relative">
    <button
      class="nb-btn px-2.5 py-1.5 text-sm"
      :aria-label="t('theme.menu')"
      :aria-expanded="open"
      aria-haspopup="true"
      :title="t('theme.menu')"
      @click="open = !open"
    >
      <span aria-hidden="true">🎨</span>
      <span class="hidden lg:inline">{{ activeLabel }}</span>
    </button>

    <div
      v-if="open"
      class="nb-card absolute end-0 top-full z-50 mt-2 w-[19rem] p-2 sm:w-[22rem]"
      role="menu"
      :aria-label="t('theme.menu')"
    >
      <p class="mb-2 px-1 text-xs font-bold opacity-70">{{ t('theme.menu') }}</p>
      <div class="grid grid-cols-2 gap-2">
        <button
          v-for="meta in availableThemes"
          :key="meta.key"
          role="menuitemradio"
          :aria-checked="currentTheme === meta.key"
          class="rounded-brutal border-2 p-1.5 text-start transition-transform hover:-translate-y-0.5"
          :class="currentTheme === meta.key ? 'border-brand-cyan' : 'border-ink/30'"
          @click="pick(meta.key)"
        >
          <!-- Miniature of the theme: its own paper, a surface bar with 'Aa', accent dots -->
          <span
            class="block rounded p-1.5"
            :style="{ background: meta.swatch.paper }"
            aria-hidden="true"
          >
            <span
              class="flex items-center justify-between rounded px-1.5 py-1"
              :style="{ background: meta.swatch.surface }"
            >
              <span class="text-[11px] font-bold" :style="{ color: meta.swatch.ink }">Aa</span>
              <span class="flex gap-1">
                <span
                  v-for="(dot, i) in meta.swatch.accents"
                  :key="i"
                  class="inline-block h-2.5 w-2.5 rounded-full"
                  :style="{ background: dot }"
                ></span>
              </span>
            </span>
          </span>
          <span class="mt-1 flex items-center justify-between gap-1">
            <span class="truncate text-xs font-bold">{{ t(meta.labelKey) }}</span>
            <span v-if="currentTheme === meta.key" class="shrink-0 text-xs" aria-hidden="true"
              >✓</span
            >
          </span>
          <span class="block truncate text-[10px] opacity-60">{{ t(meta.descKey) }}</span>
        </button>
      </div>
    </div>
  </div>
</template>
