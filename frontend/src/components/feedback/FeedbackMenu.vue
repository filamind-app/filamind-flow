<script setup lang="ts">
/** Header "Feedback" menu — a small popover offering "Report a bug" and "Request a feature".
 *  Both open the shared report dialog (see core/feedback). Mirrors ThemeMenu / LanguageMenu:
 *  click-outside + Esc to close. Marked data-feedback-noshot so it never lands in a screenshot. */
import { onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { openReport, type ReportMode } from '@/core/feedback'

const { t } = useI18n({ useScope: 'global' })

const open = ref(false)
const root = ref<HTMLElement | null>(null)

function pick(mode: ReportMode): void {
  open.value = false
  openReport(mode)
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
  <div ref="root" class="relative" data-feedback-noshot>
    <button
      class="nb-btn px-2.5 py-1.5 text-sm"
      :aria-label="t('shell.feedback.menu')"
      :aria-expanded="open"
      aria-haspopup="true"
      :title="t('shell.feedback.menu')"
      @click="open = !open"
    >
      <span aria-hidden="true">💬</span>
      <span class="hidden lg:inline">{{ t('shell.feedback.menu') }}</span>
    </button>

    <div
      v-if="open"
      class="nb-card absolute end-0 top-full z-50 mt-2 w-60 p-1.5"
      role="menu"
      :aria-label="t('shell.feedback.menuTitle')"
    >
      <p class="mb-1 px-1.5 text-xs font-bold opacity-70">{{ t('shell.feedback.menuTitle') }}</p>
      <button
        role="menuitem"
        class="flex w-full items-start gap-2 rounded-brutal px-2 py-1.5 text-start hover:bg-ink/10"
        @click="pick('bug')"
      >
        <span aria-hidden="true">🐞</span>
        <span class="min-w-0">
          <span class="block text-sm font-bold">{{ t('shell.feedback.bug') }}</span>
          <span class="block text-[11px] opacity-60">{{ t('shell.feedback.bugDesc') }}</span>
        </span>
      </button>
      <button
        role="menuitem"
        class="flex w-full items-start gap-2 rounded-brutal px-2 py-1.5 text-start hover:bg-ink/10"
        @click="pick('feature')"
      >
        <span aria-hidden="true">💡</span>
        <span class="min-w-0">
          <span class="block text-sm font-bold">{{ t('shell.feedback.feature') }}</span>
          <span class="block text-[11px] opacity-60">{{ t('shell.feedback.featureDesc') }}</span>
        </span>
      </button>
    </div>
  </div>
</template>
