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
  setPort,
  setWrites,
  updateComponent,
} from './api'
import SetupHelpIllo from './SetupHelpIllo.vue'
import type { SetupActionResult, SetupComponent, SetupComponentStatus, SetupGroup } from './types'

const { t } = useI18n()

const groups = ref<SetupGroup[]>([])
const status = ref<Record<string, SetupComponentStatus>>({})
const writesEnabled = ref(false)
const suiteCommand = ref('')
const copied = ref(false)
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

/** Installable from the GUI: git_repo / service (clone + install.sh), or any FilaMind app (which
 *  ships its own one-line installer). Third-party web / manual stay CLI-only. */
const INSTALLABLE_TYPES = new Set(['git_repo', 'service'])
const canInstall = (c: SetupComponent): boolean => INSTALLABLE_TYPES.has(c.type) || !!c.first_party

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
    suiteCommand.value = st.suiteCommand
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

async function copySuiteCommand(): Promise<void> {
  try {
    await navigator.clipboard.writeText(suiteCommand.value)
    copied.value = true
    setTimeout(() => (copied.value = false), 1500)
  } catch {
    /* clipboard unavailable; the command is shown for manual copy */
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

const isWeb = (c: SetupComponent): boolean => c.type === 'web'
function applyPort(c: SetupComponent): void {
  const port = ports.value[c.id]
  if (port) void run(c.id, () => setPort(c.id, port))
}

/** Install with live progress: start the background task, then poll it and stream its log into the
 *  card until it finishes. A refusal (writes-off / missing-deps) still arrives as a synchronous 403. */
async function doInstall(c: SetupComponent): Promise<void> {
  if (busyId.value) return
  busyId.value = c.id
  lastResult.value = null
  installLog.value = ''
  try {
    const taskId = await installComponentStream(c.id)
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
        <button class="nb-btn px-3 py-1.5" :disabled="loading" @click="load">
          {{ t('setup.refresh') }}
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

    <section v-if="!loading && !error && suiteCommand" class="nb-card bg-brand-cyan/15 p-3">
      <h3 class="font-display text-sm font-bold">{{ t('setup.suite.title') }}</h3>
      <p class="mt-1 text-sm text-ink/70">{{ t('setup.suite.intro') }}</p>
      <div class="mt-2 flex flex-wrap items-center gap-2">
        <code class="nb-card flex-1 overflow-x-auto bg-surface px-2 py-1 font-mono text-xs">{{
          suiteCommand
        }}</code>
        <button class="nb-btn px-3 py-1 text-sm" @click="copySuiteCommand">
          {{ copied ? t('setup.suite.copied') : t('setup.suite.copy') }}
        </button>
      </div>
    </section>

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
      <h3 class="font-display text-sm font-bold uppercase tracking-wide text-ink/60">
        {{ humanizeGroup(g.group) }}
      </h3>
      <ul class="flex flex-col gap-2">
        <li v-for="c in g.components" :key="c.id" class="nb-card flex flex-col gap-2 p-3">
          <div class="flex flex-wrap items-center gap-2">
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
            <span
              v-if="isInstalled(c) && installedVersion(c)"
              class="nb-badge bg-surface font-mono text-xs"
              :title="t('setup.versionInstalled')"
            >
              {{ installedVersion(c)
              }}<template v-if="updateAvailable(c) && latestVersion(c)">
                → {{ latestVersion(c) }}</template
              >
            </span>
            <span
              v-else-if="!isInstalled(c) && latestVersion(c)"
              class="nb-badge bg-surface font-mono text-xs text-ink/60"
              :title="t('setup.versionLatest')"
            >
              {{ latestVersion(c) }}
            </span>

            <span class="ms-auto flex items-center gap-2">
              <template v-if="isInstalled(c)">
                <button
                  v-if="updateAvailable(c)"
                  class="nb-btn px-3 py-1"
                  :disabled="!writesEnabled || busyId !== null"
                  @click="doUpdate(c)"
                >
                  {{ busyId === c.id ? t('setup.working') : t('setup.update') }}
                </button>
                <span v-else class="nb-badge bg-brand-green/15 text-xs text-ink/60">
                  {{ t('setup.upToDate') }}
                </span>
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
                <button
                  v-if="canInstall(c)"
                  class="nb-btn px-3 py-1"
                  :disabled="!writesEnabled || busyId !== null"
                  @click="doInstall(c)"
                >
                  {{ busyId === c.id ? t('setup.working') : t('setup.install') }}
                </button>
                <span
                  v-else
                  class="nb-badge bg-surface text-xs text-ink/70"
                  :title="t('setup.cliOnlyHint')"
                >
                  {{ t('setup.cliOnly') }}
                </span>
              </template>
            </span>
          </div>

          <p v-if="c.desc" class="text-sm text-ink/70">{{ c.desc }}</p>

          <div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink/60">
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

          <div
            v-if="isInstalled(c) && isWeb(c) && c.id in ports"
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
            class="nb-card max-h-48 overflow-auto bg-surface p-2 text-xs whitespace-pre-wrap"
            aria-live="polite"
            >{{ installLog }}</pre
          >
          <pre
            v-else-if="lastResult && lastResult.id === c.id"
            class="nb-card max-h-48 overflow-auto p-2 text-xs whitespace-pre-wrap"
            :class="lastResult.ok ? 'bg-surface' : 'bg-brand-red/20'"
            :role="lastResult.ok ? undefined : 'alert'"
            >{{ lastResult.text }}</pre
          >
        </li>
      </ul>
    </section>
  </div>
</template>
