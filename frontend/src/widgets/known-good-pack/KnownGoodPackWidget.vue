<script setup lang="ts">
/** Known-Good Packs (suite-only / flow-A): snapshot every printer config file as a restorable
 *  bundle, then roll back to it after a bad edit. Create is read-only; restore is a gated write
 *  (refused while printing) and needs a Klipper restart to take effect.
 */
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import HelpDrawer from '@/components/ui/HelpDrawer.vue'
import { describeError } from '@/core/describeError'

import HelpIllo from './HelpIllo.vue'
import { GLOSSARY_KEYS, HELP_ILLO, HELP_TOPICS } from './help'
import { createPack, deletePack, listPacks, restorePack } from './api'
import type { KgpPack } from './types'

const { t, locale } = useI18n({ useScope: 'global' })
const tt = t as unknown as (key: string, named?: Record<string, unknown>) => string

const packs = ref<KgpPack[]>([])
const label = ref('')
const error = ref<string | null>(null)
const notice = ref<{ text: string; ok: boolean } | null>(null)
const loading = ref(false)
const creating = ref(false)
const busyId = ref<string | null>(null)
const confirmRestore = ref<string | null>(null)
const confirmDelete = ref<string | null>(null)

function when(seconds: number): string {
  return new Date(seconds * 1000).toLocaleString(locale.value)
}

async function refresh(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    packs.value = await listPacks()
  } catch (e) {
    error.value = describeError(e)
  } finally {
    loading.value = false
  }
}

async function doCreate(): Promise<void> {
  creating.value = true
  error.value = null
  notice.value = null
  try {
    await createPack(label.value.trim())
    label.value = ''
    await refresh()
  } catch (e) {
    error.value = describeError(e)
  } finally {
    creating.value = false
  }
}

async function doRestore(id: string): Promise<void> {
  confirmRestore.value = null
  busyId.value = id
  error.value = null
  notice.value = null
  try {
    const res = await restorePack(id)
    notice.value = { text: tt(`knownGoodPack.restore.${res.code}`, res.params ?? {}), ok: res.ok }
  } catch (e) {
    error.value = describeError(e)
  } finally {
    busyId.value = null
  }
}

async function doDelete(id: string): Promise<void> {
  confirmDelete.value = null
  busyId.value = id
  error.value = null
  try {
    await deletePack(id)
    await refresh()
  } catch (e) {
    error.value = describeError(e)
  } finally {
    busyId.value = null
  }
}

onMounted(refresh)
</script>

<template>
  <div class="space-y-3 text-sm">
    <div class="flex items-start justify-between gap-2">
      <p class="min-w-0 flex-1 text-xs opacity-70">{{ t('knownGoodPack.intro') }}</p>
      <HelpDrawer
        class="shrink-0"
        namespace="knownGoodPack"
        :topics="HELP_TOPICS"
        :illo-map="HELP_ILLO"
        :illo="HelpIllo"
        :glossary-keys="GLOSSARY_KEYS"
        :button-label="t('knownGoodPack.help.guide')"
        :title="t('knownGoodPack.help.guideTitle')"
        :close-label="t('knownGoodPack.help.close')"
      />
    </div>

    <p v-if="error" class="nb-card bg-brand-red px-2 py-1 text-xs text-paper" role="alert">
      {{ error }}
    </p>
    <p
      v-if="notice"
      class="nb-card px-2 py-1 text-xs"
      :class="notice.ok ? 'bg-brand-lime' : 'bg-brand-yellow text-ink'"
      role="status"
    >
      {{ notice.text }}
    </p>

    <!-- Create a pack -->
    <div class="nb-card flex flex-wrap items-end gap-2 bg-surface p-2">
      <label class="flex min-w-40 flex-1 flex-col gap-0.5 text-xs">
        {{ t('knownGoodPack.create.label') }}
        <input
          v-model="label"
          type="text"
          class="nb-input"
          :placeholder="t('knownGoodPack.create.placeholder')"
        />
      </label>
      <button class="nb-btn bg-brand-lime px-3 py-1" :disabled="creating" @click="doCreate">
        {{ t('knownGoodPack.create.button') }}
      </button>
    </div>

    <p v-if="!packs.length && !loading" class="text-xs opacity-60">
      {{ t('knownGoodPack.empty') }}
    </p>

    <!-- Saved packs -->
    <ul class="space-y-2">
      <li v-for="p in packs" :key="p.id" class="nb-card space-y-1 bg-surface p-2">
        <div class="flex items-center justify-between gap-2">
          <span class="min-w-0 truncate font-bold">{{ p.label }}</span>
          <span class="shrink-0 text-[11px] opacity-60">{{ when(p.created) }}</span>
        </div>
        <p class="text-[11px] opacity-70">{{ t('knownGoodPack.files', { n: p.file_count }) }}</p>
        <div class="flex flex-wrap gap-2">
          <template v-if="confirmRestore === p.id">
            <span class="text-[11px]">{{ t('knownGoodPack.restore.confirm') }}</span>
            <button
              class="nb-btn bg-brand-cyan px-2 py-0.5 text-xs"
              :disabled="busyId === p.id"
              @click="doRestore(p.id)"
            >
              {{ t('knownGoodPack.restore.button') }}
            </button>
            <button class="nb-btn bg-surface px-2 py-0.5 text-xs" @click="confirmRestore = null">
              {{ t('knownGoodPack.cancel') }}
            </button>
          </template>
          <button
            v-else
            class="nb-btn bg-brand-cyan px-2 py-0.5 text-xs"
            :disabled="busyId === p.id"
            @click="confirmRestore = p.id"
          >
            {{ t('knownGoodPack.restore.button') }}
          </button>

          <template v-if="confirmDelete === p.id">
            <button
              class="nb-btn bg-brand-red px-2 py-0.5 text-xs text-paper"
              :disabled="busyId === p.id"
              @click="doDelete(p.id)"
            >
              {{ t('knownGoodPack.delete.confirm') }}
            </button>
            <button class="nb-btn bg-surface px-2 py-0.5 text-xs" @click="confirmDelete = null">
              {{ t('knownGoodPack.cancel') }}
            </button>
          </template>
          <button
            v-else
            class="nb-btn bg-surface px-2 py-0.5 text-xs"
            :disabled="busyId === p.id"
            @click="confirmDelete = p.id"
          >
            {{ t('knownGoodPack.delete.button') }}
          </button>
        </div>
      </li>
    </ul>

    <p class="text-[11px] opacity-60">{{ t('knownGoodPack.restore.note') }}</p>
  </div>
</template>
