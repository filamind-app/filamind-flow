<script setup lang="ts">
/** Host Control · Services — a general systemd unit manager.
 *
 *  Lists every .service unit with its state, and lets the user start / stop / restart / enable /
 *  disable / mask / unmask each one, read its journal, and delete a user-installed unit file.
 *  Destructive actions need an inline confirm; deleting a unit file needs the name typed exactly.
 *  The backend is the real guard (it refuses destructive actions on a protected set and path-guards
 *  deletion) — the UI mirrors those rules so dangerous buttons are clearly marked. */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { describeError } from '@/core/describeError'

import {
  deleteService,
  fetchServiceDetail,
  fetchServiceLogs,
  fetchServices,
  HostActionError,
  serviceAction,
} from './api'
import type { ServiceAction, ServiceDetail, ServiceUnit } from './types'

const { t } = useI18n({ useScope: 'global' })

const services = ref<ServiceUnit[]>([])
const loading = ref(true)
const error = ref<string | null>(null)

const query = ref('')
type Filter = 'all' | 'active' | 'inactive' | 'failed' | 'enabled'
const filter = ref<Filter>('all')

const selected = ref<string | null>(null)
const detail = ref<ServiceDetail | null>(null)
const detailLoading = ref(false)
const logs = ref('')
const logsLoading = ref(false)
const logLines = ref(200)

const busy = ref(false)
const actionNote = ref<string | null>(null)
const actionError = ref<string | null>(null)
const pending = ref<ServiceAction | null>(null)
const confirmDelete = ref(false)
const deleteText = ref('')

const ALL_ACTIONS: ServiceAction[] = [
  'start',
  'stop',
  'restart',
  'enable',
  'disable',
  'mask',
  'unmask',
]
const DESTRUCTIVE: ServiceAction[] = ['stop', 'restart', 'disable', 'mask']

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    services.value = await fetchServices()
  } catch (e) {
    error.value = describeError(e)
  } finally {
    loading.value = false
  }
}

onMounted(load)

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  return services.value.filter((s) => {
    if (q && !s.name.toLowerCase().includes(q) && !s.description.toLowerCase().includes(q))
      return false
    switch (filter.value) {
      case 'active':
        return s.active
      case 'inactive':
        return !s.active
      case 'failed':
        return s.active_state === 'failed'
      case 'enabled':
        return s.enabled === 'enabled'
      default:
        return true
    }
  })
})

const counts = computed(() => ({
  all: services.value.length,
  active: services.value.filter((s) => s.active).length,
  failed: services.value.filter((s) => s.active_state === 'failed').length,
}))

function resetDetailState(): void {
  detail.value = null
  logs.value = ''
  actionNote.value = null
  actionError.value = null
  pending.value = null
  confirmDelete.value = false
  deleteText.value = ''
}

async function select(name: string): Promise<void> {
  if (selected.value === name) {
    selected.value = null
    resetDetailState()
    return
  }
  selected.value = name
  resetDetailState()
  await Promise.all([loadDetail(name), loadLogs(name)])
}

async function loadDetail(name: string): Promise<void> {
  detailLoading.value = true
  try {
    detail.value = await fetchServiceDetail(name)
  } catch (e) {
    actionError.value = describeError(e)
  } finally {
    detailLoading.value = false
  }
}

async function loadLogs(name: string): Promise<void> {
  logsLoading.value = true
  try {
    logs.value = await fetchServiceLogs(name, logLines.value)
  } catch (e) {
    logs.value = ''
    actionError.value = describeError(e)
  } finally {
    logsLoading.value = false
  }
}

function isDestructive(a: ServiceAction): boolean {
  return DESTRUCTIVE.includes(a)
}

/** Disable an action that wouldn't make sense for the unit's current state, or that's protected. */
function actionDisabled(a: ServiceAction): boolean {
  const d = detail.value
  if (!d) return true
  if (d.protected && isDestructive(a)) return true
  switch (a) {
    case 'start':
      return d.active_state === 'active'
    case 'stop':
      return d.active_state !== 'active'
    case 'enable':
      return d.enabled === 'enabled' || d.enabled === 'static'
    case 'disable':
      return d.enabled !== 'enabled'
    case 'mask':
      return d.enabled === 'masked'
    case 'unmask':
      return d.enabled !== 'masked'
    default:
      return false
  }
}

function onActionClick(a: ServiceAction): void {
  actionNote.value = null
  actionError.value = null
  if (isDestructive(a)) {
    pending.value = a // show inline confirm
  } else {
    void runAction(a)
  }
}

async function runAction(a: ServiceAction): Promise<void> {
  if (!selected.value) return
  busy.value = true
  actionNote.value = null
  actionError.value = null
  try {
    const res = await serviceAction(selected.value, a)
    if (res.ok) {
      actionNote.value = res.output || t('hostControl.services.actionOk', { action: a })
    } else {
      actionError.value = res.needs_setup
        ? t('hostControl.system.needsSetup')
        : res.output || t('hostControl.services.actionFailed', { action: a })
    }
    await Promise.all([load(), loadDetail(selected.value)])
  } catch (e) {
    actionError.value = e instanceof HostActionError ? e.message : describeError(e)
  } finally {
    busy.value = false
    pending.value = null
  }
}

function cancelDelete(): void {
  confirmDelete.value = false
  deleteText.value = ''
}

async function runDelete(): Promise<void> {
  if (!selected.value) return
  busy.value = true
  actionNote.value = null
  actionError.value = null
  try {
    const res = await deleteService(selected.value, deleteText.value)
    if (res.ok) {
      actionNote.value = res.output || t('hostControl.services.deleted')
      confirmDelete.value = false
      deleteText.value = ''
      selected.value = null
      resetDetailState()
      await load()
    } else {
      actionError.value = res.needs_setup
        ? t('hostControl.system.needsSetup')
        : res.output || t('hostControl.services.deleteFailed')
    }
  } catch (e) {
    actionError.value = e instanceof HostActionError ? e.message : describeError(e)
  } finally {
    busy.value = false
  }
}

/** A short status glyph + label for a unit row. */
function stateLabel(s: ServiceUnit): string {
  if (s.active_state === 'failed') return t('hostControl.services.stateFailed')
  if (s.active) return t('hostControl.services.stateActive')
  return t('hostControl.services.stateInactive')
}
</script>

<template>
  <div class="space-y-3">
    <p class="nb-card bg-brand-yellow/15 p-2 text-[11px] leading-snug" role="note">
      ⚠ {{ t('hostControl.services.warning') }}
    </p>

    <!-- Toolbar: search + refresh -->
    <div class="flex flex-wrap items-center gap-2">
      <input
        v-model="query"
        type="search"
        :placeholder="t('hostControl.services.search')"
        class="min-w-0 flex-1 rounded-brutal border-2 border-ink bg-paper px-2 py-1 text-xs"
      />
      <button type="button" class="nb-btn text-xs" :disabled="loading" @click="load">
        ↻ {{ t('hostControl.services.refresh') }}
      </button>
    </div>

    <!-- Filter chips -->
    <div class="-mx-1 overflow-x-auto px-1">
      <div class="inline-flex overflow-hidden rounded-brutal border-2 border-ink" role="group">
        <button
          v-for="f in ['all', 'active', 'inactive', 'failed', 'enabled'] as Filter[]"
          :key="f"
          type="button"
          class="nb-seg whitespace-nowrap text-[11px]"
          :class="filter === f ? 'bg-ink text-surface' : 'bg-surface text-ink hover:bg-brand-cyan'"
          :aria-pressed="filter === f"
          @click="filter = f"
        >
          {{ t('hostControl.services.filter.' + f) }}
        </button>
      </div>
    </div>

    <p class="font-mono text-[11px] opacity-60">
      {{
        t('hostControl.services.summary', {
          total: counts.all,
          active: counts.active,
          failed: counts.failed,
        })
      }}
    </p>

    <p v-if="loading" class="font-mono text-xs opacity-70">
      {{ t('hostControl.services.loading') }}
    </p>
    <p v-else-if="error" role="alert" class="nb-card bg-brand-red/10 p-2 font-mono text-xs">
      {{ error }}
    </p>

    <!-- Service list -->
    <ul v-else class="space-y-1">
      <li v-for="s in filtered" :key="s.name" class="nb-card overflow-hidden bg-surface">
        <button
          type="button"
          class="flex w-full items-center gap-2 p-2 text-start hover:bg-brand-cyan/10"
          :aria-expanded="selected === s.name"
          @click="select(s.name)"
        >
          <span
            class="h-2.5 w-2.5 shrink-0 rounded-full border border-ink"
            :class="
              s.active_state === 'failed'
                ? 'bg-brand-red'
                : s.active
                  ? 'bg-brand-green'
                  : 'bg-transparent'
            "
            :title="stateLabel(s)"
          />
          <span class="min-w-0 flex-1">
            <span class="flex flex-wrap items-center gap-x-2 font-mono text-xs font-bold">
              {{ s.name }}
              <span
                v-if="s.critical"
                class="rounded border border-ink bg-brand-yellow/40 px-1 text-[9px] uppercase tracking-wide"
                >{{
                  s.protected
                    ? t('hostControl.services.protected')
                    : t('hostControl.services.critical')
                }}</span
              >
            </span>
            <span v-if="s.description" class="block truncate text-[11px] opacity-60">{{
              s.description
            }}</span>
          </span>
          <span class="shrink-0 font-mono text-[10px] uppercase opacity-50">{{ s.enabled }}</span>
        </button>

        <!-- Detail / actions for the selected unit -->
        <div
          v-if="selected === s.name"
          class="space-y-2 border-t-2 border-ink bg-paper p-2 text-[11px]"
        >
          <p v-if="detailLoading" class="font-mono opacity-60">
            {{ t('hostControl.services.loadingDetail') }}
          </p>
          <template v-else-if="detail">
            <dl class="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 font-mono">
              <dt class="opacity-60">{{ t('hostControl.services.state') }}</dt>
              <dd>{{ detail.active_state }} / {{ detail.sub_state }}</dd>
              <dt class="opacity-60">{{ t('hostControl.services.startup') }}</dt>
              <dd>{{ detail.enabled || '—' }}</dd>
              <dt v-if="detail.fragment_path" class="opacity-60">
                {{ t('hostControl.services.unitFile') }}
              </dt>
              <dd v-if="detail.fragment_path" class="truncate">{{ detail.fragment_path }}</dd>
            </dl>

            <!-- Action buttons -->
            <div class="flex flex-wrap gap-1">
              <button
                v-for="a in ALL_ACTIONS"
                :key="a"
                type="button"
                class="nb-btn text-[11px]"
                :class="isDestructive(a) ? 'border-brand-red text-brand-red' : ''"
                :disabled="busy || actionDisabled(a)"
                @click="onActionClick(a)"
              >
                {{ t('hostControl.services.action.' + a) }}
              </button>
            </div>

            <!-- Inline confirm for a destructive action -->
            <div
              v-if="pending"
              class="nb-card flex flex-wrap items-center gap-2 bg-brand-red/10 p-2"
              role="alertdialog"
            >
              <span class="flex-1">{{
                t('hostControl.services.confirmAction', {
                  action: t('hostControl.services.action.' + pending),
                  name: s.name,
                })
              }}</span>
              <button
                type="button"
                class="nb-btn border-brand-red text-[11px] text-brand-red"
                :disabled="busy"
                @click="runAction(pending)"
              >
                {{ t('hostControl.services.confirmYes') }}
              </button>
              <button
                type="button"
                class="nb-btn text-[11px]"
                :disabled="busy"
                @click="pending = null"
              >
                {{ t('hostControl.services.cancel') }}
              </button>
            </div>

            <!-- Delete unit file (only when the backend says it's safe) -->
            <div v-if="detail.can_delete" class="space-y-1 border-t border-ink/20 pt-2">
              <button
                v-if="!confirmDelete"
                type="button"
                class="nb-btn border-brand-red text-[11px] text-brand-red"
                :disabled="busy"
                @click="confirmDelete = true"
              >
                🗑 {{ t('hostControl.services.deleteUnit') }}
              </button>
              <div v-else class="nb-card space-y-1.5 bg-brand-red/10 p-2">
                <p>{{ t('hostControl.services.deletePrompt', { name: s.name }) }}</p>
                <input
                  v-model="deleteText"
                  type="text"
                  class="w-full rounded-brutal border-2 border-ink bg-paper px-2 py-1 font-mono text-[11px]"
                  :placeholder="s.name"
                />
                <div class="flex gap-1">
                  <button
                    type="button"
                    class="nb-btn border-brand-red text-[11px] text-brand-red"
                    :disabled="busy || deleteText !== detail.name"
                    @click="runDelete"
                  >
                    {{ t('hostControl.services.deleteConfirm') }}
                  </button>
                  <button
                    type="button"
                    class="nb-btn text-[11px]"
                    :disabled="busy"
                    @click="cancelDelete"
                  >
                    {{ t('hostControl.services.cancel') }}
                  </button>
                </div>
              </div>
            </div>

            <p v-if="actionNote" class="font-mono text-brand-green">{{ actionNote }}</p>
            <p v-if="actionError" role="alert" class="font-mono text-brand-red">
              {{ actionError }}
            </p>

            <!-- Logs -->
            <details class="border-t border-ink/20 pt-2">
              <summary class="cursor-pointer font-bold uppercase tracking-wide opacity-70">
                {{ t('hostControl.services.logs') }}
              </summary>
              <div class="mt-1 flex items-center gap-2">
                <button
                  type="button"
                  class="nb-btn text-[11px]"
                  :disabled="logsLoading"
                  @click="loadLogs(s.name)"
                >
                  ↻ {{ t('hostControl.services.refresh') }}
                </button>
                <span v-if="logsLoading" class="font-mono opacity-60">{{
                  t('hostControl.services.loadingLogs')
                }}</span>
              </div>
              <pre
                class="mt-1 max-h-64 overflow-auto rounded-brutal border-2 border-ink bg-ink p-2 font-mono text-[10px] leading-tight text-surface"
                >{{ logs || t('hostControl.services.noLogs') }}</pre
              >
            </details>
          </template>
        </div>
      </li>
    </ul>
  </div>
</template>
