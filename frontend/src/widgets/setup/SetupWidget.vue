<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import HelpDrawer from '@/components/ui/HelpDrawer.vue'

import {
  fetchCatalog,
  fetchStatus,
  installComponent,
  removeComponent,
  updateComponent,
} from './api'
import SetupHelpIllo from './SetupHelpIllo.vue'
import type { SetupComponent, SetupGroup } from './types'

const { t } = useI18n()

const groups = ref<SetupGroup[]>([])
const status = ref<Record<string, string>>({})
const writesEnabled = ref(false)
const loading = ref(true)
const error = ref<string | null>(null)

const busyId = ref<string | null>(null)
const confirmRemoveId = ref<string | null>(null)
const actionError = ref<string | null>(null)

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const [catalog, st] = await Promise.all([fetchCatalog(), fetchStatus()])
    groups.value = catalog.groups
    status.value = st.status
    writesEnabled.value = st.writesEnabled
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

async function refreshStatus(): Promise<void> {
  try {
    status.value = (await fetchStatus()).status
  } catch {
    /* keep the last status; the action result already reported */
  }
}

const isInstalled = (c: SetupComponent): boolean => status.value[c.id] === 'installed'

function humanizeGroup(id: string): string {
  return id
    .split('-')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

async function run(id: string, op: () => Promise<unknown>): Promise<void> {
  if (busyId.value) return
  busyId.value = id
  actionError.value = null
  try {
    await op()
    await refreshStatus()
  } catch (e) {
    actionError.value = e instanceof Error ? e.message : String(e)
  } finally {
    busyId.value = null
    confirmRemoveId.value = null
  }
}

const doInstall = (c: SetupComponent): Promise<void> => run(c.id, () => installComponent(c.id))
const doUpdate = (c: SetupComponent): Promise<void> => run(c.id, () => updateComponent(c.id))
function onRemove(c: SetupComponent): void {
  if (confirmRemoveId.value === c.id) void run(c.id, () => removeComponent(c.id, c.id))
  else confirmRemoveId.value = c.id
}

onMounted(load)
</script>

<template>
  <div class="flex flex-col gap-4">
    <header class="flex items-center justify-between gap-3">
      <p class="text-sm text-ink/70">{{ t('setup.intro') }}</p>
      <div class="flex shrink-0 items-center gap-2">
        <HelpDrawer
          namespace="setup"
          :topics="['overview']"
          :illo-map="{}"
          :illo="SetupHelpIllo"
          :glossary-keys="[]"
          :button-label="t('setup.help.button')"
          :title="t('setup.help.title')"
          :close-label="t('setup.help.close')"
        />
        <button class="nb-btn px-3 py-1.5" :disabled="loading" @click="load">
          {{ t('setup.refresh') }}
        </button>
      </div>
    </header>

    <p v-if="!loading && !writesEnabled" class="nb-card bg-brand-yellow/30 p-3 text-sm" role="note">
      {{ t('setup.writesDisabled') }}
    </p>
    <p v-if="actionError" class="nb-card bg-brand-red/20 p-3 text-sm" role="alert">
      {{ actionError }}
    </p>

    <p v-if="loading" class="text-sm text-ink/70">{{ t('setup.working') }}</p>
    <p v-else-if="error" class="nb-card bg-brand-red/20 p-3 text-sm" role="alert">{{ error }}</p>

    <section v-for="g in groups" v-else :key="g.group" class="flex flex-col gap-2">
      <h3 class="font-display text-sm font-bold uppercase tracking-wide text-ink/60">
        {{ humanizeGroup(g.group) }}
      </h3>
      <ul class="flex flex-col gap-2">
        <li
          v-for="c in g.components"
          :key="c.id"
          class="nb-card flex flex-wrap items-center gap-2 p-3"
        >
          <span class="font-bold">{{ c.name }}</span>
          <span class="nb-badge bg-surface text-xs">{{ c.kind }}</span>
          <span v-if="c.first_party" class="nb-badge bg-brand-cyan text-xs">{{
            t('setup.firstParty')
          }}</span>
          <span
            class="nb-badge text-xs"
            :class="isInstalled(c) ? 'bg-brand-green' : 'bg-surface text-ink/70'"
          >
            {{ isInstalled(c) ? t('setup.installed') : t('setup.available') }}
          </span>

          <span class="ms-auto flex items-center gap-2">
            <template v-if="isInstalled(c)">
              <button
                class="nb-btn px-3 py-1"
                :disabled="!writesEnabled || busyId !== null"
                @click="doUpdate(c)"
              >
                {{ t('setup.update') }}
              </button>
              <button
                class="nb-btn px-3 py-1"
                :class="{ 'bg-brand-red text-paper': confirmRemoveId === c.id }"
                :disabled="!writesEnabled || busyId !== null"
                @click="onRemove(c)"
              >
                {{ confirmRemoveId === c.id ? t('setup.removeConfirm') : t('setup.remove') }}
              </button>
            </template>
            <button
              v-else
              class="nb-btn px-3 py-1"
              :disabled="!writesEnabled || busyId !== null"
              @click="doInstall(c)"
            >
              {{ busyId === c.id ? t('setup.working') : t('setup.install') }}
            </button>
          </span>
        </li>
      </ul>
    </section>
  </div>
</template>
