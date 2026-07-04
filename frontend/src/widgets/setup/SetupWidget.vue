<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import HelpDrawer from '@/components/ui/HelpDrawer.vue'

import { fetchTask } from '@/core/tasks'

import {
  fetchCatalog,
  fetchStatus,
  installComponentStream,
  removeComponent,
  restartComponent,
  setAutoUpdate,
  setPort,
  setWrites,
  updateComponent,
} from './api'
import SetupHelpIllo from './SetupHelpIllo.vue'
import type {
  SetupActionResult,
  SetupAutoUpdate,
  SetupComponent,
  SetupComponentStatus,
  SetupGroup,
} from './types'

const { t } = useI18n()

const groups = ref<SetupGroup[]>([])
const status = ref<Record<string, SetupComponentStatus>>({})
const writesEnabled = ref(false)
const autoUpdate = ref<SetupAutoUpdate>({ enabled: false, intervalHours: 24 })
const loading = ref(true)
const error = ref<string | null>(null)

const query = ref('')
/** Per-web-UI port the user is editing (seeded from each component's default_port). */
const ports = ref<Record<string, number>>({})
const busyId = ref<string | null>(null)
const confirmRemoveId = ref<string | null>(null)
/** The result of the most recent action, shown on the card that triggered it (ok or refused). */
const lastResult = ref<{ id: string; text: string; ok: boolean } | null>(null)
/** Live install output for the card currently installing (streamed from the background task). */
const installLog = ref('')

/** Auto-update interval choices (hours): 6h, 12h, daily, 2 days, weekly. */
const INTERVALS = [6, 12, 24, 48, 168] as const

/** One-click installable from the GUI: git_repo / service (clone + install.sh), or any FilaMind app
 *  (which ships its own one-line installer). Third-party web UIs / manual add-ons install on host. */
const INSTALLABLE_TYPES = new Set(['git_repo', 'service'])
const canInstall = (c: SetupComponent): boolean => INSTALLABLE_TYPES.has(c.type) || !!c.first_party

/** A first-party app with an ADDITIONAL managed deployment installable by its own button (FilaMind
 *  3d → agent). When service_install equals install_args it IS the main install (FilaMind screen),
 *  so no extra button is shown. */
const hasService = (c: SetupComponent): boolean =>
  !!c.first_party && !!c.service_install && c.service_install !== (c.install_args ?? '')

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const [catalog, st] = await Promise.all([fetchCatalog(), fetchStatus()])
    groups.value = catalog.groups
    for (const g of catalog.groups)
      for (const c of g.components)
        if (c.type === 'web' && c.default_port && !(c.id in ports.value))
          ports.value[c.id] = c.default_port
    status.value = st.status
    writesEnabled.value = st.writesEnabled
    autoUpdate.value = st.autoUpdate ?? { enabled: false, intervalHours: 24 }
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

const isInstalled = (c: SetupComponent): boolean => status.value[c.id]?.status === 'installed'
/** An installed component that Moonraker reports is behind its remote (drives the Update button). */
const updateAvailable = (c: SetupComponent): boolean => status.value[c.id]?.updateAvailable === true
const installedVersion = (c: SetupComponent): string => status.value[c.id]?.version ?? ''
/** Latest available version: remote for installed components, latest release/tag for not-installed. */
const latestVersion = (c: SetupComponent): string => status.value[c.id]?.latest ?? ''

/** Every component flattened by id, for resolving dependency ids to display names. */
const byId = computed<Record<string, SetupComponent>>(() => {
  const map: Record<string, SetupComponent> = {}
  for (const g of groups.value) for (const c of g.components) map[c.id] = c
  return map
})

const totals = computed(() => {
  const all = Object.values(byId.value)
  return { total: all.length, installed: all.filter(isInstalled).length }
})

/** How many installed components have an update waiting (drives "Update all"). */
const updateCount = computed(() => Object.values(byId.value).filter(updateAvailable).length)

/** Groups filtered by the search box (matches name, description, kind or id). */
const filteredGroups = computed<SetupGroup[]>(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return groups.value
  return groups.value
    .map((g) => ({
      group: g.group,
      components: g.components.filter((c) =>
        [c.name, c.desc ?? '', c.kind, c.id].some((f) => f.toLowerCase().includes(q)),
      ),
    }))
    .filter((g) => g.components.length > 0)
})

const hasResults = computed(() => filteredGroups.value.length > 0)

const depNames = (c: SetupComponent): string[] =>
  (c.deps ?? []).map((id) => byId.value[id]?.name ?? id)

const repoUrl = (c: SetupComponent): string => `https://github.com/${c.repo}`

function humanizeGroup(id: string): string {
  return id
    .split('-')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

async function run(id: string, op: () => Promise<SetupActionResult>): Promise<void> {
  if (busyId.value) return
  busyId.value = id
  lastResult.value = null // clear any stale output from a previous action
  try {
    const result = await op()
    lastResult.value = result.output ? { id, text: result.output, ok: true } : null
    await refreshStatus()
  } catch (e) {
    // A refusal (dependency guard / writes-disabled) or fault: show it on the triggering card.
    lastResult.value = { id, text: e instanceof Error ? e.message : String(e), ok: false }
  } finally {
    busyId.value = null
    confirmRemoveId.value = null
  }
}

const enablingWrites = ref(false)
async function enableWrites(): Promise<void> {
  enablingWrites.value = true
  error.value = null
  try {
    writesEnabled.value = await setWrites(true)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    enablingWrites.value = false
  }
}

/** A first-party web app (FilaMind 3d): we serve its own nginx site, so we can both install it on a
 *  chosen port and change that port later. Third-party web UIs (Mainsail/Fluidd) are host-managed. */
const isFirstPartyWeb = (c: SetupComponent): boolean => c.type === 'web' && !!c.first_party
function applyPort(c: SetupComponent): void {
  const port = ports.value[c.id]
  if (port) void run(c.id, () => setPort(c.id, port))
}

/** Runtime status for an installed first-party app served by nginx (FilaMind 3d / screen): the
 *  backend reports the served port + whether it actually responds. These drive the running/stopped
 *  badge, the open link, and the restart button. */
const appPort = (c: SetupComponent): number | undefined => status.value[c.id]?.port
const hasRuntime = (c: SetupComponent): boolean => isInstalled(c) && appPort(c) !== undefined
const isRunning = (c: SetupComponent): boolean => status.value[c.id]?.running === true
/** Same-origin host + the app's port, so "Open" navigates the current tab to the app. */
const appUrl = (c: SetupComponent): string => {
  const port = appPort(c)
  return port ? `${window.location.protocol}//${window.location.hostname}:${port}/` : '#'
}
const doRestart = (c: SetupComponent): Promise<void> => run(c.id, () => restartComponent(c.id))

/** Install with live progress: start the background task, then poll it and stream its log into the
 *  card until it finishes. `action: 'service'` installs a first-party app's extra deployment (3d →
 *  agent). A refusal (writes-off / missing-deps) still arrives as a synchronous 403. */
async function doInstall(c: SetupComponent, action?: string): Promise<void> {
  if (busyId.value) return
  busyId.value = c.id
  lastResult.value = null
  installLog.value = ''
  try {
    // First-party web app: install straight onto the chosen port (e.g. 88 when Mainsail owns 80).
    const port = !action && isFirstPartyWeb(c) ? ports.value[c.id] : undefined
    const taskId = await installComponentStream(c.id, port, action)
    for (;;) {
      await new Promise((r) => setTimeout(r, 1000))
      const task = await fetchTask(taskId)
      installLog.value = task.log
      if (task.status !== 'running') {
        const out = (task.result?.output as string) || task.log || ''
        lastResult.value = out ? { id: c.id, text: out, ok: task.status === 'done' } : null
        break
      }
    }
    await refreshStatus()
  } catch (e) {
    // A refusal (403) or fault: show it on the triggering card, like the other actions.
    lastResult.value = { id: c.id, text: e instanceof Error ? e.message : String(e), ok: false }
  } finally {
    busyId.value = null
    installLog.value = ''
    confirmRemoveId.value = null
  }
}
const doUpdate = (c: SetupComponent): Promise<void> => run(c.id, () => updateComponent(c.id))
function onRemove(c: SetupComponent): void {
  if (confirmRemoveId.value === c.id) void run(c.id, () => removeComponent(c.id, c.id))
  else confirmRemoveId.value = c.id
}

/** Update every component that has an update waiting, one after another. */
async function updateAll(): Promise<void> {
  if (busyId.value) return
  for (const c of Object.values(byId.value).filter(updateAvailable))
    await run(c.id, () => updateComponent(c.id))
}

/** Persist the auto-update toggle / interval the moment it changes. */
async function saveAutoUpdate(): Promise<void> {
  error.value = null
  try {
    autoUpdate.value = await setAutoUpdate(autoUpdate.value.enabled, autoUpdate.value.intervalHours)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
}

onMounted(load)
</script>

<template>
  <div class="flex flex-col gap-4">
    <header class="flex flex-wrap items-center justify-between gap-3">
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
        <button
          v-if="updateCount > 0"
          class="nb-btn bg-brand-green px-3 py-1.5"
          :disabled="!writesEnabled || busyId !== null"
          @click="updateAll"
        >
          {{ t('setup.updateAll', { n: updateCount }) }}
        </button>
        <button class="nb-btn px-3 py-1.5" :disabled="loading || busyId !== null" @click="load">
          {{ t('setup.checkUpdates') }}
        </button>
      </div>
    </header>

    <div v-if="!loading && !error" class="flex flex-wrap items-center gap-3">
      <input
        v-model="query"
        type="search"
        class="nb-input min-w-48 flex-1 px-3 py-1.5 text-sm"
        :placeholder="t('setup.search')"
        :aria-label="t('setup.search')"
      />
      <span class="nb-badge bg-surface text-xs">
        {{ t('setup.summary', { installed: totals.installed, total: totals.total }) }}
      </span>
    </div>

    <!-- Periodic auto-update (opt-in): keeps everything current, but only while the printer is idle. -->
    <div
      v-if="!loading && !error && writesEnabled"
      class="nb-card flex flex-wrap items-center gap-x-4 gap-y-2 p-3 text-sm"
    >
      <label class="flex items-center gap-2 font-bold">
        <input
          v-model="autoUpdate.enabled"
          type="checkbox"
          class="h-4 w-4 accent-brand-cyan"
          @change="saveAutoUpdate"
        />
        {{ t('setup.autoUpdate.title') }}
      </label>
      <span
        class="flex items-center gap-2 text-xs"
        :class="{ 'pointer-events-none opacity-50': !autoUpdate.enabled }"
      >
        <label for="autoupdate-interval" class="text-ink/60">{{
          t('setup.autoUpdate.every')
        }}</label>
        <select
          id="autoupdate-interval"
          v-model.number="autoUpdate.intervalHours"
          class="nb-input px-2 py-1"
          :disabled="!autoUpdate.enabled"
          @change="saveAutoUpdate"
        >
          <option v-for="h in INTERVALS" :key="h" :value="h">
            {{ t(`setup.autoUpdate.opt${h}`) }}
          </option>
        </select>
      </span>
      <span class="text-[11px] text-ink/55">{{ t('setup.autoUpdate.hint') }}</span>
    </div>

    <div
      v-if="!loading && !writesEnabled"
      class="nb-card flex flex-wrap items-center gap-3 bg-brand-yellow/30 p-3 text-sm"
      role="note"
    >
      <span class="flex-1">{{ t('setup.writesOff') }}</span>
      <button class="nb-btn px-3 py-1" :disabled="enablingWrites" @click="enableWrites">
        {{ enablingWrites ? t('setup.working') : t('setup.enableWrites') }}
      </button>
    </div>

    <p v-if="loading" class="text-sm text-ink/70">{{ t('setup.working') }}</p>
    <p v-else-if="error" class="nb-card bg-brand-red/20 p-3 text-sm" role="alert">{{ error }}</p>
    <p v-else-if="!hasResults" class="text-sm text-ink/70">{{ t('setup.noMatch') }}</p>

    <section v-for="g in filteredGroups" v-else :key="g.group" class="flex flex-col gap-2">
      <h3 class="font-display text-xs font-bold uppercase tracking-wide text-ink/60">
        {{ humanizeGroup(g.group) }}
      </h3>
      <ul class="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        <li v-for="c in g.components" :key="c.id" class="nb-card flex flex-col gap-2 p-3">
          <!-- header: name + first-party tag + install/version, status badge on the right -->
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0">
              <div class="flex flex-wrap items-center gap-1.5">
                <span class="truncate font-bold">{{ c.name }}</span>
                <span v-if="c.first_party" class="nb-badge bg-brand-cyan text-[10px]">{{
                  t('setup.firstParty')
                }}</span>
              </div>
              <div
                class="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-ink/60"
              >
                <span>{{ c.kind }}</span>
                <span
                  v-if="isInstalled(c) && installedVersion(c)"
                  class="font-mono"
                  :title="t('setup.versionInstalled')"
                >
                  {{ installedVersion(c)
                  }}<template v-if="updateAvailable(c) && latestVersion(c)">
                    → {{ latestVersion(c) }}</template
                  >
                </span>
                <span
                  v-else-if="!isInstalled(c) && latestVersion(c)"
                  class="font-mono"
                  :title="t('setup.versionLatest')"
                >
                  {{ latestVersion(c) }}
                </span>
              </div>
            </div>
            <span
              class="nb-badge shrink-0 text-[10px]"
              :class="isInstalled(c) ? 'bg-brand-green' : 'bg-surface text-ink/70'"
            >
              {{ isInstalled(c) ? t('setup.installed') : t('setup.available') }}
            </span>
          </div>

          <p v-if="c.desc" class="line-clamp-2 text-xs text-ink/70">{{ c.desc }}</p>

          <div class="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-ink/55">
            <span v-if="depNames(c).length">
              {{ t('setup.needs') }}: {{ depNames(c).join(', ') }}
            </span>
            <a
              class="underline hover:text-ink"
              :href="repoUrl(c)"
              target="_blank"
              rel="noopener noreferrer"
            >
              {{ t('setup.repo') }}
            </a>
          </div>

          <!-- Runtime status for an installed first-party app (3d / screen): is it actually serving,
               where, with an open-in-this-tab link and a restart (reload nginx). -->
          <div v-if="hasRuntime(c)" class="flex flex-wrap items-center gap-2 text-[11px]">
            <span class="inline-flex items-center gap-1">
              <span
                class="h-2.5 w-2.5 rounded-full border border-ink"
                :class="isRunning(c) ? 'bg-brand-green' : 'bg-brand-red'"
              />
              {{ isRunning(c) ? t('setup.serving') : t('setup.notServing') }}
            </span>
            <span class="text-ink/60">{{ t('setup.port') }} {{ appPort(c) }}</span>
            <a class="nb-btn px-2.5 py-0.5" :href="appUrl(c)">{{ t('setup.open') }}</a>
            <button
              class="nb-btn px-2.5 py-0.5"
              :disabled="!writesEnabled || busyId !== null"
              @click="doRestart(c)"
            >
              {{ busyId === c.id ? t('setup.working') : t('setup.restart') }}
            </button>
          </div>

          <!-- actions footer, pinned to the bottom so cards in a row line up -->
          <div class="mt-auto flex flex-wrap items-center gap-1.5 pt-1">
            <template v-if="isInstalled(c)">
              <button
                v-if="updateAvailable(c)"
                class="nb-btn px-3 py-1"
                :disabled="!writesEnabled || busyId !== null"
                @click="doUpdate(c)"
              >
                {{ busyId === c.id ? t('setup.working') : t('setup.update') }}
              </button>
              <span v-else class="nb-badge bg-brand-green/15 text-[10px] text-ink/60">
                {{ t('setup.upToDate') }}
              </span>
              <button
                v-if="hasService(c)"
                class="nb-btn px-3 py-1"
                :disabled="!writesEnabled || busyId !== null"
                :title="c.service_install_hint"
                @click="doInstall(c, 'service')"
              >
                {{ t('setup.installNamed', { x: c.service_install }) }}
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
            <template v-else>
              <span
                v-if="isFirstPartyWeb(c) && c.id in ports"
                class="flex items-center gap-1 text-xs"
              >
                <label :for="`install-port-${c.id}`" class="text-ink/60">{{
                  t('setup.port')
                }}</label>
                <input
                  :id="`install-port-${c.id}`"
                  v-model.number="ports[c.id]"
                  type="number"
                  min="1"
                  max="65535"
                  class="nb-input w-20 px-2 py-1"
                />
              </span>
              <button
                v-if="canInstall(c)"
                class="nb-btn px-3 py-1"
                :disabled="!writesEnabled || busyId !== null"
                @click="doInstall(c)"
              >
                {{ busyId === c.id ? t('setup.working') : t('setup.install') }}
              </button>
              <a
                v-else
                class="nb-btn px-3 py-1"
                :href="repoUrl(c)"
                target="_blank"
                rel="noopener noreferrer"
                :title="t('setup.onHostHint')"
              >
                {{ t('setup.onHost') }}
              </a>
              <button
                v-if="hasService(c)"
                class="nb-btn px-3 py-1"
                :disabled="!writesEnabled || busyId !== null"
                :title="c.service_install_hint"
                @click="doInstall(c, 'service')"
              >
                {{ t('setup.installNamed', { x: c.service_install }) }}
              </button>
            </template>
          </div>

          <div
            v-if="isInstalled(c) && c.type === 'web' && c.id in ports"
            class="flex flex-wrap items-center gap-2 text-xs"
          >
            <label :for="`port-${c.id}`" class="text-ink/60">{{ t('setup.port') }}</label>
            <input
              :id="`port-${c.id}`"
              v-model.number="ports[c.id]"
              type="number"
              min="1"
              max="65535"
              class="nb-input w-24 px-2 py-1"
            />
            <button
              class="nb-btn px-3 py-1"
              :disabled="!writesEnabled || busyId !== null"
              @click="applyPort(c)"
            >
              {{ t('setup.portApply') }}
            </button>
          </div>

          <!-- Live install progress: the streaming log while this card is installing. -->
          <pre
            v-if="busyId === c.id && installLog"
            class="nb-card max-h-40 overflow-auto bg-surface p-2 text-[11px] whitespace-pre-wrap"
            aria-live="polite"
            >{{ installLog }}</pre>
          <pre
            v-else-if="lastResult && lastResult.id === c.id"
            class="nb-card max-h-40 overflow-auto p-2 text-[11px] whitespace-pre-wrap"
            :class="lastResult.ok ? 'bg-surface' : 'bg-brand-red/20'"
            :role="lastResult.ok ? undefined : 'alert'"
            >{{ lastResult.text }}</pre>
        </li>
      </ul>
    </section>
  </div>
</template>
