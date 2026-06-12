<script setup lang="ts">
/** Shared "Apply to printer.cfg" flow — the tuning widgets' last mile.
 *
 *  Takes a ready config block (an `[input_shaper]` result, a driver tune) and writes it through
 *  the Config Editor's proven gate: pick the target file, review the block, acknowledge, apply
 *  (param-level merge server-side — an existing section keeps its other params), then optionally
 *  trigger the separately-confirmed FIRMWARE_RESTART. Busy (409) and changed-on-disk (412)
 *  refusals surface as clear messages. */
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import ComboSelect from '@/components/ui/ComboSelect.vue'
import { describeError } from '@/core/describeError'
import {
  ApiError,
  applySection,
  type ApplySectionChange,
  fetchConfigFiles,
  restartFirmware,
} from '@/widgets/config-editor/api'

const props = withDefaults(
  defineProps<{
    /** The config block to merge (one or more [section]s). */
    block: string
    /** Pre-selected target file. */
    defaultFile?: string
  }>(),
  { defaultFile: 'printer.cfg' },
)

const { t } = useI18n({ useScope: 'global' })

const files = ref<{ value: string; label: string }[]>([])
const target = ref<string | null>(props.defaultFile)
const ack = ref(false)
const busy = ref(false)
const error = ref<string | null>(null)
const changes = ref<ApplySectionChange[] | null>(null)
const savedBackup = ref<string | null>(null)
const confirmRestart = ref(false)
const restarting = ref(false)
const restartMsg = ref<string | null>(null)

onMounted(() => {
  fetchConfigFiles()
    .then((r) => {
      files.value = r.files.map((f) => ({ value: f.path, label: f.path }))
    })
    .catch(() => {
      /* picker degrades to the default filename */
    })
})

async function apply(): Promise<void> {
  if (!target.value || !props.block.trim()) return
  busy.value = true
  error.value = null
  changes.value = null
  restartMsg.value = null
  try {
    const result = await applySection(target.value, props.block)
    changes.value = result.changes
    savedBackup.value = result.backup
    ack.value = false
  } catch (e) {
    if (e instanceof ApiError && e.status === 409) error.value = t('configApply.busy')
    else if (e instanceof ApiError && e.status === 412) error.value = t('configApply.stale')
    else error.value = describeError(e)
  } finally {
    busy.value = false
  }
}

async function doRestart(): Promise<void> {
  restarting.value = true
  error.value = null
  try {
    await restartFirmware()
    restartMsg.value = t('configApply.restarted')
    confirmRestart.value = false
  } catch (e) {
    error.value =
      e instanceof ApiError && e.status === 409 ? t('configApply.busy') : describeError(e)
  } finally {
    restarting.value = false
  }
}

function changeLine(c: ApplySectionChange): string {
  return t(c.action === 'added' ? 'configApply.added' : 'configApply.updated', {
    section: c.section,
    params: c.params.join(', '),
  })
}
</script>

<template>
  <div class="space-y-2 text-[11px]">
    <p class="opacity-70">{{ t('configApply.hint') }}</p>

    <label class="block">
      <span class="mb-1 block text-[10px] font-bold opacity-70">{{ t('configApply.target') }}</span>
      <ComboSelect v-model="target" :options="files" :placeholder="props.defaultFile" />
    </label>

    <pre
      class="max-h-40 overflow-auto rounded border border-ink/30 bg-ink/5 p-1.5 font-mono text-[10px] leading-snug"
      >{{ props.block }}</pre
    >

    <div class="flex flex-wrap items-center gap-2">
      <label class="flex items-center gap-1.5">
        <input v-model="ack" type="checkbox" />
        <span>{{ t('configApply.ack') }}</span>
      </label>
      <button
        class="nb-btn bg-brand-cyan px-3 py-1 text-xs"
        :disabled="!ack || busy || !target"
        @click="apply"
      >
        {{ busy ? t('configApply.applying') : t('configApply.apply') }}
      </button>
    </div>

    <p v-if="error" role="alert" class="nb-card bg-brand-red/10 p-2 font-mono text-[10px]">
      {{ error }}
    </p>

    <div v-if="changes" role="status" class="nb-card space-y-1.5 bg-brand-lime/20 p-2">
      <p class="font-bold">{{ t('configApply.saved', { backup: savedBackup ?? '—' }) }}</p>
      <ul v-if="changes.length" class="space-y-0.5 font-mono text-[10px]">
        <li v-for="(c, i) in changes" :key="i">• {{ changeLine(c) }}</li>
      </ul>
      <p v-else class="font-mono text-[10px] opacity-70">{{ t('configApply.noop') }}</p>

      <template v-if="changes.length">
        <p class="text-[10px] opacity-70">{{ t('configApply.restartHint') }}</p>
        <div class="flex flex-wrap items-center gap-2">
          <button
            v-if="!confirmRestart"
            class="nb-btn bg-surface px-2 py-1 text-xs"
            @click="confirmRestart = true"
          >
            {{ t('configApply.restart') }}
          </button>
          <template v-else>
            <button
              class="nb-btn bg-brand-red px-2 py-1 text-xs text-paper"
              :disabled="restarting"
              @click="doRestart"
            >
              {{ restarting ? t('configApply.restarting') : t('configApply.restartConfirm') }}
            </button>
            <button class="nb-btn bg-surface px-2 py-1 text-xs" @click="confirmRestart = false">
              {{ t('configApply.cancel') }}
            </button>
          </template>
          <span v-if="restartMsg" class="font-bold">{{ restartMsg }}</span>
        </div>
      </template>
    </div>
  </div>
</template>
