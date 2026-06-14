<script setup lang="ts">
/** A tiny inline "⚐ Report" control to drop next to any error message. Clicking opens the shared
 *  bug-report dialog pre-filled with the error text (and an auto-captured screenshot), so a user
 *  can turn a failure into a GitHub issue in two clicks. Renders nothing when there's no error. */
import { useI18n } from 'vue-i18n'

import { openReport } from '@/core/feedback'

const props = defineProps<{ error?: string | null }>()

const { t } = useI18n({ useScope: 'global' })

function report(): void {
  if (props.error) openReport('bug', { error: props.error })
}
</script>

<template>
  <button
    v-if="error"
    type="button"
    class="nb-btn shrink-0 bg-surface px-1.5 py-0.5 text-[10px]"
    :title="t('shell.feedback.reportErrorAria')"
    :aria-label="t('shell.feedback.reportErrorAria')"
    @click="report"
  >
    <span aria-hidden="true">⚐</span> {{ t('shell.feedback.reportError') }}
  </button>
</template>
