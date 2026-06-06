<script setup lang="ts">
/** Flash-confirmation gate (#111). Stands between any "flash" action and the firmware write:
 *  it previews the flash plan (command + warnings + ready) for a single device when a request is
 *  given, and requires an explicit "I understand" acknowledgement before proceeding. Flashing is
 *  destructive and can brick a board if interrupted, so NOTHING writes until the user confirms.
 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { fetchFlashPlan } from './api'
import type { FlashIntent, FlashPlan } from './types'

const { t } = useI18n({ useScope: 'global' })

const props = defineProps<{ intent: FlashIntent }>()
const emit = defineEmits<{ confirm: []; cancel: [] }>()

const plan = ref<FlashPlan | null>(null)
const planError = ref<string | null>(null)
const loadingPlan = ref(false)
const confirmed = ref(false)

onMounted(async () => {
  if (!props.intent.request) return
  loadingPlan.value = true
  try {
    plan.value = await fetchFlashPlan(props.intent.request)
  } catch (e) {
    planError.value = e instanceof Error ? e.message : t('firmware.flashConfirm.previewFailed')
  } finally {
    loadingPlan.value = false
  }
})

// Block proceeding only when we have a plan that is explicitly not ready (e.g. a print is running).
const blocked = computed(() => plan.value !== null && plan.value.ready === false)
</script>

<template>
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-ink/60 p-4"
    role="dialog"
    aria-modal="true"
    @click.self="emit('cancel')"
  >
    <div
      class="w-full max-w-md space-y-2 rounded-brutal border-3 border-ink bg-paper p-3 text-sm shadow-brutal"
    >
      <div class="flex items-center justify-between gap-2">
        <span class="text-xs font-bold uppercase tracking-wide">{{
          t('firmware.flashConfirm.title')
        }}</span>
        <button class="nb-btn bg-surface px-2 py-0.5 text-[11px]" @click="emit('cancel')">
          {{ t('firmware.flashConfirm.cancel') }}
        </button>
      </div>

      <p class="font-bold">{{ intent.title }}</p>
      <p class="rounded-brutal border-2 border-ink bg-brand-yellow px-2 py-1 text-[11px]">
        ⚠ {{ intent.warning }}
      </p>

      <ul v-if="intent.devices?.length" class="font-mono text-[11px] opacity-80">
        <li v-for="d in intent.devices" :key="d">• {{ d }}</li>
      </ul>

      <p v-if="loadingPlan" class="font-mono text-[11px] opacity-60">
        {{ t('firmware.flashConfirm.previewing') }}
      </p>
      <div v-else-if="plan" class="space-y-1 rounded-brutal border-2 border-ink p-2">
        <div class="flex items-center justify-between gap-2">
          <span class="min-w-0 truncate font-mono text-[11px]"
            >{{ plan.method }} → {{ plan.artifact ?? '—' }}</span
          >
          <span
            class="nb-badge shrink-0 text-[11px]"
            :class="plan.ready ? 'bg-brand-lime' : 'bg-brand-yellow'"
            >{{
              plan.ready ? t('firmware.flashConfirm.ready') : t('firmware.flashConfirm.blocked')
            }}</span
          >
        </div>
        <pre
          class="overflow-x-auto rounded-brutal border-2 border-ink bg-ink p-1.5 font-mono text-[11px] text-surface"
          >{{ plan.command }}</pre
        >
        <p v-for="w in plan.warnings" :key="w" class="font-mono text-[11px] text-brand-red">
          ⚠ {{ w }}
        </p>
      </div>
      <p v-else-if="planError" class="font-mono text-[11px] text-brand-red">
        {{ t('firmware.flashConfirm.planErrorSuffix', { error: planError }) }}
      </p>

      <label class="flex items-start gap-1.5 text-[11px]">
        <input v-model="confirmed" type="checkbox" class="mt-0.5 shrink-0" />
        <span>{{ t('firmware.flashConfirm.acknowledge') }}</span>
      </label>
      <button
        class="nb-btn w-full bg-brand-red py-1 text-xs text-surface"
        :disabled="!confirmed || blocked"
        @click="emit('confirm')"
      >
        {{
          blocked
            ? t('firmware.flashConfirm.blockedSeeWarnings')
            : t('firmware.flashConfirm.flashNow')
        }}
      </button>
    </div>
  </div>
</template>
