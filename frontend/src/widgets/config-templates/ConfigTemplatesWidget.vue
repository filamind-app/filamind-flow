<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import ConfigApply from '@/components/ui/ConfigApply.vue'
import { useI18n } from 'vue-i18n'

import ComboSelect from '@/components/ui/ComboSelect.vue'
import HelpDrawer from '@/components/ui/HelpDrawer.vue'
import { describeError } from '@/core/describeError'

import { fetchTemplates } from './api'
import HelpIllo from './HelpIllo.vue'
import { GLOSSARY_KEYS, HELP_ILLO, HELP_TOPICS } from './help'
import type { ConfigTemplate } from './types'

const { t, te } = useI18n({ useScope: 'global' })

// Backend categories are English data values — translate via a slug key when one
// exists, otherwise show the raw value (future categories degrade gracefully).
function categoryLabel(c: string): string {
  const key = `configTemplates.categories.${c.toLowerCase().replace(/[^a-z0-9]+/g, '_')}`
  return te(key) ? t(key) : c
}

const templates = ref<ConfigTemplate[]>([])
const category = ref<string | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)
const copiedId = ref<string | null>(null)

const categories = computed(() => [...new Set(templates.value.map((x) => x.category))])
const categoryOptions = computed(() =>
  categories.value.map((c) => ({ value: c, label: categoryLabel(c) })),
)
const filtered = computed(() =>
  category.value ? templates.value.filter((x) => x.category === category.value) : templates.value,
)

async function load(): Promise<void> {
  loading.value = true
  try {
    templates.value = await fetchTemplates()
    error.value = null
  } catch (e) {
    error.value = describeError(e)
  } finally {
    loading.value = false
  }
}

/** Copy that works on a plain-http LAN host (where navigator.clipboard is unavailable). */
async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    // fall through to the legacy path
  }
  try {
    const ta = document.createElement('textarea')
    ta.value = text
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(ta)
    return ok
  } catch {
    return false
  }
}

async function copy(tpl: ConfigTemplate): Promise<void> {
  if (await copyText(tpl.body)) {
    copiedId.value = tpl.id
    window.setTimeout(() => {
      if (copiedId.value === tpl.id) copiedId.value = null
    }, 1500)
  }
}

onMounted(() => void load())
</script>

<template>
  <div class="space-y-3 text-sm">
    <!-- Intro + help -->
    <div class="flex items-start justify-between gap-2">
      <p class="min-w-0 flex-1 text-xs opacity-70">{{ t('configTemplates.intro') }}</p>
      <div class="flex shrink-0 items-center gap-2">
        <HelpDrawer
          namespace="configTemplates"
          :topics="HELP_TOPICS"
          :illo-map="HELP_ILLO"
          :illo="HelpIllo"
          :glossary-keys="GLOSSARY_KEYS"
          steps-key="configTemplates.help.steps"
          :button-label="t('configTemplates.help.guide')"
          :title="t('configTemplates.help.guideTitle')"
          :close-label="t('configTemplates.help.close')"
          :steps-title="t('configTemplates.help.howToRead')"
        />
        <HelpIllo illo="template" class="h-8 w-8 opacity-70" />
      </div>
    </div>

    <!-- Filter -->
    <div class="flex flex-wrap items-end gap-2">
      <label class="min-w-[12rem] flex-1">
        <span class="mb-0.5 block text-[11px] opacity-70">{{
          t('configTemplates.category.label')
        }}</span>
        <ComboSelect
          v-model="category"
          :options="categoryOptions"
          :placeholder="t('configTemplates.category.all')"
          clearable
        />
      </label>
      <span class="nb-card bg-surface px-2 py-1 font-mono text-[11px]">
        {{ t('configTemplates.count', { n: filtered.length }) }}
      </span>
    </div>

    <!-- States -->
    <p v-if="loading" class="font-mono text-xs opacity-70">
      {{ t('configTemplates.states.loading') }}
    </p>
    <div v-else-if="error" class="nb-card space-y-2 bg-brand-red/10 p-2">
      <p class="font-mono text-xs">{{ t('configTemplates.states.error') }}</p>
      <p class="font-mono text-[11px] opacity-70">{{ error }}</p>
      <button class="nb-btn bg-surface px-2 py-1 text-xs" @click="load">
        {{ t('configTemplates.states.retry') }}
      </button>
    </div>
    <p v-else-if="!filtered.length" class="font-mono text-xs opacity-70">
      {{ t('configTemplates.states.empty') }}
    </p>

    <!-- Templates -->
    <ul v-else class="space-y-2">
      <li v-for="tpl in filtered" :key="tpl.id" class="nb-card space-y-1.5 bg-surface p-2">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <span class="font-bold">{{ tpl.name }}</span>
          <span class="shrink-0 rounded bg-brand-cyan px-1.5 py-0.5 text-[10px] font-bold text-ink">
            {{ categoryLabel(tpl.category) }}
          </span>
        </div>
        <p class="text-[11px] opacity-80">{{ tpl.description }}</p>
        <p v-if="tpl.required_sections?.length" class="font-mono text-[10px] opacity-60">
          {{
            t('configTemplates.template.requires', { sections: tpl.required_sections.join(', ') })
          }}
        </p>
        <pre
          class="overflow-auto rounded-brutal border-2 border-ink bg-paper p-2 font-mono text-[10px] leading-snug"
        ><code>{{ tpl.body }}</code></pre>
        <button class="nb-btn bg-surface px-2 py-1 text-xs" @click="copy(tpl)">
          <span aria-hidden="true">⧉</span>
          {{
            copiedId === tpl.id
              ? t('configTemplates.template.copied')
              : t('configTemplates.template.copy')
          }}
        </button>

        <!-- Write it straight into the config behind the shared gate (no copy-paste). -->
        <details class="nb-card mt-1 bg-surface p-2">
          <summary class="cursor-pointer text-[11px] font-bold">
            {{ t('configApply.title') }}
          </summary>
          <div class="mt-2">
            <ConfigApply :block="tpl.body" />
          </div>
        </details>
      </li>
    </ul>
  </div>
</template>
