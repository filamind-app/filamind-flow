<script setup lang="ts">
/** The shared report dialog (mounted once at the app shell). Composes a bug report or feature
 *  request from the shared feedback state, shows the diagnostics that will be attached, and on
 *  submit opens a pre-filled GitHub issue in a new tab — it never posts anything by itself.
 *  Marked data-feedback-noshot so it's excluded from the screenshot. */
import { computed, nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import {
  closeReport,
  collectDiagnostics,
  feedback,
  submitReport,
  type Diagnostics,
} from '@/core/feedback'

const { t } = useI18n({ useScope: 'global' })

const description = ref('')
const diag = ref<Diagnostics | null>(null)
const descEl = ref<HTMLTextAreaElement | null>(null)
// The element focused before the dialog opened, so focus can return there on close.
let lastFocused: HTMLElement | null = null

const isBug = computed(() => feedback.mode === 'bug')
const canSubmit = computed(
  () => description.value.trim().length > 0 || feedback.errorText.length > 0,
)

// Reset the form and snapshot the diagnostics each time the dialog opens (so the timestamp
// doesn't tick while it's on screen).
watch(
  () => feedback.open,
  (open) => {
    if (open) {
      lastFocused = (document.activeElement as HTMLElement) ?? null
      description.value = ''
      diag.value = collectDiagnostics()
      void nextTick(() => descEl.value?.focus())
    } else {
      // Return focus to whatever opened the dialog (the menu item or error button).
      lastFocused?.focus?.()
      lastFocused = null
    }
  },
)

function onKey(e: KeyboardEvent): void {
  if (e.key === 'Escape') closeReport()
}
watch(
  () => feedback.open,
  (open) => {
    if (open) window.addEventListener('keydown', onKey)
    else window.removeEventListener('keydown', onKey)
  },
)

function submit(): void {
  if (!canSubmit.value) return
  submitReport(description.value)
}

const diagRows = computed(() => {
  const d = diag.value
  if (!d) return [] as { label: string; value: string }[]
  return [
    { label: t('shell.feedback.field.version'), value: d.version },
    { label: t('shell.feedback.field.view'), value: d.view },
    { label: t('shell.feedback.field.locale'), value: d.locale },
    { label: t('shell.feedback.field.theme'), value: d.theme },
    { label: t('shell.feedback.field.screen'), value: d.screen },
    { label: t('shell.feedback.field.browser'), value: d.userAgent },
    { label: t('shell.feedback.field.time'), value: d.time },
  ]
})
</script>

<template>
  <Teleport to="body">
    <div
      v-if="feedback.open"
      data-feedback-noshot
      class="fixed inset-0 z-[60] flex items-center justify-center p-4"
    >
      <div class="absolute inset-0 bg-ink/50" @click="closeReport" />

      <div
        class="nb-card relative z-10 flex max-h-[90vh] w-full max-w-lg flex-col overflow-hidden bg-paper p-0"
        role="dialog"
        aria-modal="true"
        :aria-label="
          isBug ? t('shell.feedback.dialog.bugTitle') : t('shell.feedback.dialog.featureTitle')
        "
      >
        <header
          class="flex items-center justify-between gap-2 border-b-3 border-ink p-3"
          :class="isBug ? 'bg-brand-yellow' : 'bg-brand-cyan'"
        >
          <h2 class="font-display text-lg font-bold">
            <span aria-hidden="true">{{ isBug ? '🐞' : '💡' }}</span>
            {{
              isBug ? t('shell.feedback.dialog.bugTitle') : t('shell.feedback.dialog.featureTitle')
            }}
          </h2>
          <button
            class="nb-btn bg-surface px-2 py-1 text-xs"
            :aria-label="t('shell.feedback.dialog.cancel')"
            @click="closeReport"
          >
            <span aria-hidden="true">✕</span>
          </button>
        </header>

        <!-- Form phase -->
        <div
          v-if="feedback.phase === 'form'"
          class="min-h-0 flex-1 space-y-3 overflow-y-auto p-3 text-sm"
        >
          <p class="opacity-80">
            {{
              isBug ? t('shell.feedback.dialog.introBug') : t('shell.feedback.dialog.introFeature')
            }}
          </p>

          <label class="block space-y-1">
            <span class="text-xs font-bold">{{ t('shell.feedback.dialog.descLabel') }}</span>
            <textarea
              ref="descEl"
              v-model="description"
              rows="4"
              maxlength="4000"
              class="w-full rounded-brutal border-2 border-ink bg-surface p-2 text-sm"
              :placeholder="
                isBug
                  ? t('shell.feedback.dialog.descPlaceholderBug')
                  : t('shell.feedback.dialog.descPlaceholderFeature')
              "
            ></textarea>
          </label>

          <!-- Error text carried in from a "Report this error" button -->
          <div v-if="feedback.errorText" class="space-y-1">
            <span class="text-xs font-bold">{{ t('shell.feedback.field.error') }}</span>
            <pre
              class="max-h-24 overflow-auto rounded-brutal border-2 border-ink bg-ink p-2 font-mono text-[11px] text-surface"
              >{{ feedback.errorText }}</pre
            >
          </div>

          <!-- Screenshot (bug only) -->
          <div v-if="isBug" class="rounded-brutal border-2 border-ink bg-surface p-2">
            <label class="flex items-center gap-2">
              <input v-model="feedback.attachScreenshot" type="checkbox" class="h-4 w-4" />
              <span class="text-sm font-bold">{{ t('shell.feedback.dialog.attach') }}</span>
            </label>
            <p class="mt-1 text-[11px] opacity-60">{{ t('shell.feedback.dialog.attachHint') }}</p>
            <p
              v-if="feedback.attachScreenshot && feedback.capturing"
              class="mt-1 text-[11px] opacity-70"
            >
              {{ t('shell.feedback.dialog.capturing') }}
            </p>
            <div v-else-if="feedback.attachScreenshot && feedback.screenshotUrl" class="mt-2">
              <img
                :src="feedback.screenshotUrl"
                :alt="t('shell.feedback.dialog.screenshotReady')"
                class="max-h-32 w-full rounded border-2 border-ink object-contain object-top"
              />
            </div>
            <p
              v-else-if="feedback.attachScreenshot && !feedback.capturing"
              class="mt-1 text-[11px] text-brand-red"
            >
              {{ t('shell.feedback.dialog.noScreenshot') }}
            </p>
          </div>

          <!-- What we'll include -->
          <details class="rounded-brutal border-2 border-ink bg-surface">
            <summary class="cursor-pointer px-2 py-1.5 text-xs font-bold">
              {{ t('shell.feedback.dialog.includes') }}
            </summary>
            <div class="border-t-2 border-ink/20 p-2">
              <p class="mb-2 text-[11px] opacity-60">
                {{ t('shell.feedback.dialog.includesNote') }}
              </p>
              <dl class="space-y-1 font-mono text-[11px]">
                <div v-for="row in diagRows" :key="row.label" class="flex gap-2">
                  <dt class="shrink-0 opacity-60">{{ row.label }}:</dt>
                  <dd class="min-w-0 break-all">{{ row.value }}</dd>
                </div>
              </dl>
            </div>
          </details>

          <p class="text-[11px] opacity-60">{{ t('shell.feedback.dialog.languageNote') }}</p>
        </div>

        <!-- Sent phase -->
        <div v-else class="min-h-0 flex-1 space-y-3 overflow-y-auto p-3 text-sm">
          <p class="font-bold">
            <span aria-hidden="true">✅</span> {{ t('shell.feedback.sent.title') }}
          </p>
          <p class="opacity-80">{{ t('shell.feedback.sent.body') }}</p>
          <p
            v-if="feedback.screenshotMethod === 'clipboard'"
            class="nb-card bg-brand-cyan/15 p-2 text-[12px]"
          >
            <span aria-hidden="true">📋</span> {{ t('shell.feedback.sent.copied') }}
          </p>
          <p
            v-else-if="feedback.screenshotMethod === 'download'"
            class="nb-card bg-brand-cyan/15 p-2 text-[12px]"
          >
            <span aria-hidden="true">💾</span> {{ t('shell.feedback.sent.saved') }}
          </p>
          <p
            v-else-if="feedback.screenshotMethod === 'failed'"
            class="nb-card bg-brand-yellow/20 p-2 text-[12px]"
          >
            <span aria-hidden="true">⚠</span> {{ t('shell.feedback.sent.failed') }}
          </p>
        </div>

        <!-- Footer -->
        <footer class="flex items-center justify-end gap-2 border-t-3 border-ink p-3">
          <template v-if="feedback.phase === 'form'">
            <button class="nb-btn bg-surface px-3 py-1.5 text-sm" @click="closeReport">
              {{ t('shell.feedback.dialog.cancel') }}
            </button>
            <button
              class="nb-btn bg-brand-lime px-3 py-1.5 text-sm"
              :disabled="!canSubmit || feedback.sending"
              @click="submit"
            >
              <span aria-hidden="true">↗</span> {{ t('shell.feedback.dialog.submit') }}
            </button>
          </template>
          <button v-else class="nb-btn bg-brand-lime px-3 py-1.5 text-sm" @click="closeReport">
            {{ t('shell.feedback.dialog.close') }}
          </button>
        </footer>
      </div>
    </div>
  </Teleport>
</template>
