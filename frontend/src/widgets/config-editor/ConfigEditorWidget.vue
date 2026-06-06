<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import ComboSelect from '@/components/ui/ComboSelect.vue'
import HelpDrawer from '@/components/ui/HelpDrawer.vue'
import WidgetTabs from '@/components/ui/WidgetTabs.vue'
import { describeError } from '@/core/describeError'

import { fetchConfigFile, fetchConfigFiles } from './api'
import HelpIllo from './HelpIllo.vue'
import { GLOSSARY_KEYS, HELP_ILLO, HELP_TOPICS } from './help'
import type { ConfigFileInfo, ConfigFileView } from './types'

const { t } = useI18n({ useScope: 'global' })

const files = ref<ConfigFileInfo[]>([])
const selected = ref<string | null>(null)
const view = ref<ConfigFileView | null>(null)
const loadingFiles = ref(true)
const loadingView = ref(false)
const errFiles = ref<string | null>(null)
const errView = ref<string | null>(null)
const viewMode = ref<'structured' | 'raw'>('structured')
/** Per-section disclosure (keyed by index, since headers can repeat — e.g. duplicate sections). */
const open = ref<Record<number, boolean>>({})

const VIEW_TABS = computed<{ id: 'structured' | 'raw'; label: string }[]>(() => [
  { id: 'structured', label: t('configEditor.view.structured') },
  { id: 'raw', label: t('configEditor.view.raw') },
])

const fileOptions = computed(() =>
  files.value.map((f) => ({
    value: f.path,
    label: f.path,
    sublabel:
      f.size != null ? t('configEditor.summary.size', { kb: (f.size / 1024).toFixed(1) }) : '',
  })),
)

const paramTotal = computed(() =>
  (view.value?.sections ?? []).reduce((n, s) => n + s.params.length, 0),
)
const errorCount = computed(
  () => (view.value?.issues ?? []).filter((i) => i.level === 'error').length,
)
const warningCount = computed(
  () => (view.value?.issues ?? []).filter((i) => i.level === 'warning').length,
)

async function loadFiles(): Promise<void> {
  loadingFiles.value = true
  try {
    const list = await fetchConfigFiles()
    files.value = list.files
    errFiles.value = null
    // Default to printer.cfg when present, else the first file.
    const printerCfg = list.files.find((f) => f.path === 'printer.cfg')
    selected.value = printerCfg?.path ?? list.files[0]?.path ?? null
  } catch (e) {
    errFiles.value = describeError(e)
  } finally {
    loadingFiles.value = false
  }
}

async function loadView(filename: string): Promise<void> {
  loadingView.value = true
  try {
    view.value = await fetchConfigFile(filename)
    errView.value = null
    open.value = {}
  } catch (e) {
    errView.value = describeError(e)
    view.value = null
  } finally {
    loadingView.value = false
  }
}

function expandAll(): void {
  const next: Record<number, boolean> = {}
  ;(view.value?.sections ?? []).forEach((_, i) => (next[i] = true))
  open.value = next
}
function collapseAll(): void {
  open.value = {}
}

watch(selected, (f) => {
  if (f) void loadView(f)
})
onMounted(() => void loadFiles())
</script>

<template>
  <div class="space-y-3 text-sm">
    <!-- Intro + help layer -->
    <div class="flex items-start justify-between gap-2">
      <p class="min-w-0 flex-1 text-xs opacity-70">{{ t('configEditor.intro') }}</p>
      <div class="flex shrink-0 items-center gap-2">
        <HelpDrawer
          namespace="configEditor"
          :topics="HELP_TOPICS"
          :illo-map="HELP_ILLO"
          :illo="HelpIllo"
          :glossary-keys="GLOSSARY_KEYS"
          steps-key="configEditor.help.steps"
          :button-label="t('configEditor.help.guide')"
          :title="t('configEditor.help.guideTitle')"
          :close-label="t('configEditor.help.close')"
          :steps-title="t('configEditor.help.howToRead')"
        />
        <HelpIllo illo="file" class="h-8 w-8 opacity-70" />
      </div>
    </div>

    <!-- File picker -->
    <div class="flex flex-wrap items-end gap-2">
      <label class="min-w-[12rem] flex-1">
        <span class="mb-1 block text-xs font-bold">{{ t('configEditor.file.label') }}</span>
        <ComboSelect
          v-model="selected"
          :options="fileOptions"
          :placeholder="t('configEditor.file.placeholder')"
          :disabled="loadingFiles || !!errFiles"
        />
      </label>
      <button
        class="nb-btn bg-surface px-2 py-1 text-xs"
        :disabled="loadingFiles"
        @click="loadFiles"
      >
        <span aria-hidden="true">↻</span> {{ t('configEditor.file.refresh') }}
      </button>
    </div>

    <!-- File-list states -->
    <p v-if="loadingFiles" class="font-mono text-xs opacity-70">
      {{ t('configEditor.file.loadingList') }}
    </p>
    <p v-else-if="errFiles" class="nb-card bg-brand-red/10 p-2 font-mono text-xs">{{ errFiles }}</p>
    <p v-else-if="!files.length" class="font-mono text-xs opacity-70">
      {{ t('configEditor.file.emptyList') }}
    </p>

    <!-- File-view states -->
    <p v-if="loadingView" class="font-mono text-xs opacity-70">
      {{ t('configEditor.states.loading') }}
    </p>
    <div v-else-if="errView" class="nb-card space-y-2 bg-brand-red/10 p-2">
      <p class="font-mono text-xs">{{ t('configEditor.states.error') }}</p>
      <p class="font-mono text-[11px] opacity-70">{{ errView }}</p>
      <button
        v-if="selected"
        class="nb-btn bg-surface px-2 py-1 text-xs"
        @click="loadView(selected)"
      >
        {{ t('configEditor.states.retry') }}
      </button>
    </div>

    <!-- Parsed view -->
    <template v-if="view && !loadingView && !errView">
      <!-- Summary -->
      <div class="flex flex-wrap items-center gap-2 font-mono text-xs">
        <span class="nb-card bg-surface px-2 py-1">
          {{ t('configEditor.summary.sections', { count: view.section_count }) }}
        </span>
        <span class="nb-card bg-surface px-2 py-1">
          {{ t('configEditor.summary.params', { count: paramTotal }) }}
        </span>
      </div>

      <!-- Validation banner -->
      <div
        class="nb-card p-2"
        :class="
          errorCount ? 'bg-brand-red/10' : warningCount ? 'bg-brand-yellow/20' : 'bg-brand-lime/20'
        "
        role="status"
      >
        <p class="mb-1 text-xs font-bold">{{ t('configEditor.validation.title') }}</p>
        <p v-if="!view.issues.length" class="font-mono text-[11px] opacity-80">
          <span aria-hidden="true">✓</span> {{ t('configEditor.validation.clean') }}
        </p>
        <ul v-else class="space-y-1">
          <li
            v-for="(issue, i) in view.issues"
            :key="i"
            class="flex items-start gap-1.5 font-mono text-[11px]"
          >
            <span
              class="shrink-0 rounded px-1 font-bold"
              :class="
                issue.level === 'error' ? 'bg-brand-red text-paper' : 'bg-brand-yellow text-ink'
              "
            >
              {{
                issue.level === 'error'
                  ? t('configEditor.validation.error')
                  : t('configEditor.validation.warning')
              }}
            </span>
            <span class="min-w-0">{{ issue.message }}</span>
          </li>
        </ul>
      </div>

      <!-- View toggle -->
      <WidgetTabs v-model="viewMode" :tabs="VIEW_TABS" />

      <!-- Structured: collapsible sections -->
      <template v-if="viewMode === 'structured'">
        <div class="flex justify-end gap-2">
          <button class="nb-btn bg-surface px-2 py-0.5 text-[11px]" @click="expandAll">
            {{ t('configEditor.view.expandAll') }}
          </button>
          <button class="nb-btn bg-surface px-2 py-0.5 text-[11px]" @click="collapseAll">
            {{ t('configEditor.view.collapseAll') }}
          </button>
        </div>

        <ul class="space-y-2">
          <li
            v-for="(section, i) in view.sections"
            :key="i"
            class="nb-card overflow-hidden bg-surface"
          >
            <button
              class="flex w-full items-center justify-between gap-2 px-2 py-1.5 text-start"
              :aria-expanded="!!open[i]"
              @click="open[i] = !open[i]"
            >
              <span class="min-w-0 truncate font-mono text-xs">
                <span aria-hidden="true">{{ open[i] ? '▾' : '▸' }}</span>
                <b>[{{ section.header }}]</b>
                <span
                  v-if="section.is_save_config"
                  class="ms-1 rounded bg-ink px-1 text-[10px] text-paper"
                >
                  {{ t('configEditor.section.saveBadge') }}
                </span>
              </span>
              <span class="shrink-0 font-mono text-[10px] opacity-60">
                {{ t('configEditor.section.paramsCount', { count: section.params.length }) }}
              </span>
            </button>

            <div v-if="open[i]" class="border-t-2 border-ink/20 px-2 py-1.5">
              <p v-if="!section.params.length" class="font-mono text-[11px] opacity-60">
                {{ t('configEditor.section.noParams') }}
              </p>
              <table v-else class="w-full border-collapse font-mono text-[11px]">
                <thead>
                  <tr class="text-start opacity-60">
                    <th class="py-0.5 pe-2 text-start font-bold">
                      {{ t('configEditor.section.paramHead') }}
                    </th>
                    <th class="py-0.5 text-start font-bold">
                      {{ t('configEditor.section.valueHead') }}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(p, pi) in section.params" :key="pi" class="align-top">
                    <td class="py-0.5 pe-2 font-bold">{{ p.key }}</td>
                    <td class="whitespace-pre-wrap break-words py-0.5">
                      {{ p.value || '—'
                      }}<span v-if="p.comment" class="opacity-50"> {{ p.comment }}</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </li>
        </ul>
      </template>

      <!-- Raw -->
      <pre
        v-else
        class="nb-card max-h-[28rem] overflow-auto bg-surface p-2 font-mono text-[11px] leading-snug"
      ><code>{{ view.raw }}</code></pre>
    </template>
  </div>
</template>
