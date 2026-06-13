<script setup lang="ts">
/** KlipperScreen Studio — edit the touchscreen's config and restart it to apply.
 *
 *  Phase 1: a safe raw editor for `KlipperScreen.conf` (gated save = timestamped backup +
 *  stale-write guard + refused while printing, reusing the Config Editor's machinery) plus a
 *  one-tap service restart. The graphical option editor + theme builder build on this. */
import { onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { describeError } from '@/core/describeError'

import {
  activateTheme,
  createTheme,
  deleteTheme,
  fetchScreenConf,
  fetchScreenStatus,
  fetchThemes,
  restartScreen,
  saveScreenConf,
  ScreenSaveError,
  type ScreenTheme,
} from './api'
import type { ScreenStatus } from './types'

const { t } = useI18n({ useScope: 'global' })

const status = ref<ScreenStatus | null>(null)
const statusError = ref<string | null>(null)
const checking = ref(true)

const content = ref('')
const sha = ref<string | null>(null)
const dirty = ref(false)
const loadingConf = ref(false)
const confError = ref<string | null>(null)

const saving = ref(false)
const saveError = ref<string | null>(null)
const saved = ref(false)

const confirmRestart = ref(false)
const restarting = ref(false)
const restarted = ref(false)
const restartError = ref<string | null>(null)

// Theme builder
type View = 'config' | 'themes'
const view = ref<View>('config')
const themes = ref<ScreenTheme[]>([])
const tokens = ref<string[]>([])
const palette = reactive<Record<string, string>>({})
const radius = ref(8)
const themeName = ref('')
const themesBusy = ref(false)
const themesError = ref<string | null>(null)
const themesNote = ref<string | null>(null)

async function loadConf(): Promise<void> {
  loadingConf.value = true
  confError.value = null
  try {
    const c = await fetchScreenConf()
    content.value = c.raw
    sha.value = c.sha256
    dirty.value = false
    saved.value = false
    saveError.value = null
  } catch (e) {
    confError.value = describeError(e)
  } finally {
    loadingConf.value = false
  }
}

async function loadStatus(): Promise<void> {
  checking.value = true
  statusError.value = null
  try {
    status.value = await fetchScreenStatus()
    if (status.value?.present && status.value.conf_exists) await loadConf()
  } catch (e) {
    statusError.value = describeError(e)
  } finally {
    checking.value = false
  }
}

function onEdit(): void {
  dirty.value = true
  saved.value = false
}

async function save(): Promise<void> {
  saving.value = true
  saveError.value = null
  try {
    const c = await saveScreenConf(content.value, sha.value)
    sha.value = c.sha256
    dirty.value = false
    saved.value = true
  } catch (e) {
    if (e instanceof ScreenSaveError && e.status === 412)
      saveError.value = t('klipperscreenStudio.save.stale')
    else if (e instanceof ScreenSaveError && e.status === 409)
      saveError.value = t('klipperscreenStudio.save.busy')
    else saveError.value = describeError(e)
  } finally {
    saving.value = false
  }
}

async function doRestart(): Promise<void> {
  confirmRestart.value = false
  restarting.value = true
  restartError.value = null
  restarted.value = false
  try {
    await restartScreen()
    restarted.value = true
  } catch (e) {
    restartError.value = describeError(e)
  } finally {
    restarting.value = false
  }
}

async function loadThemes(): Promise<void> {
  themesBusy.value = true
  themesError.value = null
  try {
    const cat = await fetchThemes()
    themes.value = cat.themes
    tokens.value = cat.tokens
    if (!Object.keys(palette).length) {
      for (const k of cat.tokens) palette[k] = cat.defaults[k] ?? '#000000'
    }
  } catch (e) {
    themesError.value = describeError(e)
  } finally {
    themesBusy.value = false
  }
}

function switchView(v: View): void {
  view.value = v
  if (v === 'themes' && !tokens.value.length) void loadThemes()
}

async function createAndApply(apply: boolean): Promise<void> {
  themesBusy.value = true
  themesError.value = null
  themesNote.value = null
  try {
    await createTheme(themeName.value.trim(), { ...palette }, radius.value)
    if (apply) {
      await activateTheme(themeName.value.trim())
      themesNote.value = t('klipperscreenStudio.themes.appliedRestart')
    } else {
      themesNote.value = t('klipperscreenStudio.themes.created')
    }
    await loadThemes()
  } catch (e) {
    themesError.value = describeError(e)
  } finally {
    themesBusy.value = false
  }
}

async function applyExisting(name: string): Promise<void> {
  themesBusy.value = true
  themesError.value = null
  themesNote.value = null
  try {
    await activateTheme(name)
    themesNote.value = t('klipperscreenStudio.themes.appliedRestart')
  } catch (e) {
    themesError.value = describeError(e)
  } finally {
    themesBusy.value = false
  }
}

async function removeTheme(name: string): Promise<void> {
  themesBusy.value = true
  themesError.value = null
  try {
    await deleteTheme(name)
    await loadThemes()
  } catch (e) {
    themesError.value = describeError(e)
  } finally {
    themesBusy.value = false
  }
}

onMounted(() => void loadStatus())
</script>

<template>
  <div class="space-y-3 text-sm">
    <p class="text-xs opacity-70">{{ t('klipperscreenStudio.intro') }}</p>

    <!-- Inline help: what this is + the safe workflow -->
    <details class="nb-card bg-surface p-2">
      <summary class="cursor-pointer text-xs font-bold uppercase tracking-wide opacity-70">
        {{ t('klipperscreenStudio.help.title') }}
      </summary>
      <div class="mt-2 space-y-1 text-[11px] opacity-80">
        <p>{{ t('klipperscreenStudio.help.body') }}</p>
        <ol class="list-decimal space-y-0.5 ps-4">
          <li>{{ t('klipperscreenStudio.help.step1') }}</li>
          <li>{{ t('klipperscreenStudio.help.step2') }}</li>
          <li>{{ t('klipperscreenStudio.help.step3') }}</li>
        </ol>
        <p class="opacity-70">{{ t('klipperscreenStudio.help.lfNote') }}</p>
      </div>
    </details>

    <p v-if="checking" class="font-mono text-xs opacity-70">
      {{ t('klipperscreenStudio.status.checking') }}
    </p>
    <p v-else-if="statusError" role="alert" class="nb-card bg-brand-red/10 p-2 font-mono text-xs">
      {{ statusError }}
    </p>
    <p v-else-if="!status?.present" class="nb-card bg-surface p-3 text-xs opacity-70">
      {{ t('klipperscreenStudio.status.absent') }}
    </p>

    <template v-else>
      <!-- Status line -->
      <div class="nb-card flex flex-wrap items-center gap-x-4 gap-y-1 bg-surface p-3 text-[11px]">
        <span class="font-bold uppercase tracking-wide opacity-60">{{
          t('klipperscreenStudio.status.present')
        }}</span>
        <span v-if="status.theme" class="font-mono"
          >{{ t('klipperscreenStudio.status.theme') }}: <b>{{ status.theme }}</b></span
        >
        <span v-if="status.language" class="font-mono"
          >{{ t('klipperscreenStudio.status.language') }}: <b>{{ status.language }}</b></span
        >
        <span v-if="!status.restartable" class="text-brand-red"
          >⚠ {{ t('klipperscreenStudio.status.notRestartable') }}</span
        >
      </div>

      <!-- Config / Themes view toggle -->
      <div class="inline-flex overflow-hidden rounded-brutal border-2 border-ink" role="group">
        <button
          v-for="v in ['config', 'themes'] as const"
          :key="v"
          type="button"
          class="nb-seg"
          :class="view === v ? 'bg-ink text-surface' : 'bg-surface text-ink hover:bg-brand-cyan'"
          :aria-pressed="view === v"
          @click="switchView(v)"
        >
          {{ t('klipperscreenStudio.view.' + v) }}
        </button>
      </div>

      <template v-if="view === 'config'">
        <!-- Raw editor -->
        <p v-if="loadingConf" class="font-mono text-xs opacity-70">
          {{ t('klipperscreenStudio.editor.loading') }}
        </p>
        <p v-else-if="confError" role="alert" class="nb-card bg-brand-red/10 p-2 font-mono text-xs">
          {{ confError }}
        </p>
        <template v-else>
          <div class="flex items-center justify-between gap-2">
            <span class="font-mono text-[11px] opacity-60">KlipperScreen.conf</span>
            <button
              class="nb-btn bg-surface px-2 py-0.5 text-[11px]"
              :disabled="loadingConf"
              @click="loadConf"
            >
              ↻ {{ t('klipperscreenStudio.editor.reload') }}
            </button>
          </div>
          <textarea
            v-model="content"
            spellcheck="false"
            dir="ltr"
            class="h-72 w-full rounded-brutal border-3 border-ink bg-paper p-2 font-mono text-[11px] leading-snug"
            @input="onEdit"
          ></textarea>

          <div class="flex flex-wrap items-center gap-2">
            <button
              class="nb-btn bg-brand-lime px-3 py-1 text-xs"
              :disabled="saving || !dirty"
              @click="save"
            >
              {{
                saving
                  ? t('klipperscreenStudio.editor.saving')
                  : t('klipperscreenStudio.editor.save')
              }}
            </button>
            <span v-if="saved" class="text-[11px] font-bold text-brand-lime"
              >✓ {{ t('klipperscreenStudio.editor.saved') }}</span
            >
            <span v-else-if="dirty" class="text-[11px] opacity-60">{{
              t('klipperscreenStudio.editor.unsaved')
            }}</span>
            <span class="flex-1"></span>
            <button
              class="nb-btn bg-brand-yellow px-3 py-1 text-xs"
              :disabled="restarting"
              @click="confirmRestart = true"
            >
              {{
                restarting
                  ? t('klipperscreenStudio.restart.restarting')
                  : t('klipperscreenStudio.restart.button')
              }}
            </button>
          </div>

          <p
            v-if="saveError"
            role="alert"
            class="nb-card bg-brand-red/10 p-2 font-mono text-[11px]"
          >
            {{ saveError }}
          </p>
          <p v-if="restarted" class="text-[11px] font-bold text-brand-lime">
            ✓ {{ t('klipperscreenStudio.restart.done') }}
          </p>
          <p
            v-if="restartError"
            role="alert"
            class="nb-card bg-brand-red/10 p-2 font-mono text-[11px]"
          >
            {{ restartError }}
          </p>

          <!-- Restart confirm -->
          <div
            v-if="confirmRestart"
            class="nb-card space-y-2 border-brand-red bg-brand-yellow/20 p-2"
          >
            <p class="text-xs font-bold">{{ t('klipperscreenStudio.restart.confirmTitle') }}</p>
            <p class="text-[11px] opacity-80">{{ t('klipperscreenStudio.restart.confirmBody') }}</p>
            <div class="flex gap-2">
              <button class="nb-btn bg-brand-red px-3 py-1 text-xs text-paper" @click="doRestart">
                {{ t('klipperscreenStudio.restart.confirm') }}
              </button>
              <button class="nb-btn bg-surface px-3 py-1 text-xs" @click="confirmRestart = false">
                {{ t('klipperscreenStudio.restart.cancel') }}
              </button>
            </div>
          </div>
        </template>
      </template>

      <!-- Themes view: palette pickers + live preview + theme management -->
      <template v-else>
        <p v-if="themesBusy && !tokens.length" class="font-mono text-xs opacity-70">
          {{ t('klipperscreenStudio.themes.loading') }}
        </p>
        <template v-else>
          <div class="grid gap-3 md:grid-cols-2">
            <!-- palette editor -->
            <div class="min-w-0 space-y-1.5">
              <p class="text-xs font-bold">{{ t('klipperscreenStudio.themes.palette') }}</p>
              <div v-for="tok in tokens" :key="tok" class="flex items-center gap-2 text-[11px]">
                <input
                  v-model="palette[tok]"
                  type="color"
                  class="h-7 w-9 shrink-0 rounded border-2 border-ink"
                  :aria-label="tok"
                />
                <span class="min-w-0 flex-1 truncate font-mono">{{ tok }}</span>
                <span class="shrink-0 font-mono opacity-60">{{ palette[tok] }}</span>
              </div>
              <label class="flex items-center gap-2 pt-1 text-[11px]">
                <span class="shrink-0 font-mono">{{ t('klipperscreenStudio.themes.radius') }}</span>
                <input
                  v-model.number="radius"
                  type="range"
                  min="0"
                  max="30"
                  class="min-w-0 flex-1"
                />
                <span class="shrink-0 font-mono">{{ radius }}px</span>
              </label>
            </div>

            <!-- live preview (an approximate mock, not the real GTK screen) -->
            <div class="min-w-0 space-y-1">
              <p class="text-xs font-bold">{{ t('klipperscreenStudio.themes.preview') }}</p>
              <div
                class="rounded-brutal border-3 border-ink p-2"
                :style="{ backgroundColor: palette.bg, color: palette.text }"
              >
                <div
                  class="mb-2 flex items-center justify-between rounded px-2 py-1 text-[11px]"
                  :style="{ backgroundColor: palette.active }"
                >
                  <span>SV08</span><span :style="{ color: palette.color3 }">●</span>
                </div>
                <div class="grid grid-cols-2 gap-1.5">
                  <div
                    v-for="(c, i) in ['color1', 'color2', 'color3', 'color4']"
                    :key="c"
                    class="border-2 px-2 py-2 text-center text-[11px] font-bold"
                    :style="{
                      backgroundColor: palette.active,
                      color: palette['text-inv'],
                      borderColor: palette[c],
                      borderRadius: radius + 'px',
                    }"
                  >
                    {{ t('klipperscreenStudio.themes.btn') }} {{ i + 1 }}
                  </div>
                </div>
                <p class="mt-2 text-[11px]" :style="{ color: palette.warning }">
                  ⚠ {{ t('klipperscreenStudio.themes.previewWarn') }}
                </p>
              </div>
              <p class="text-[11px] opacity-60">
                {{ t('klipperscreenStudio.themes.previewApprox') }}
              </p>
            </div>
          </div>

          <!-- create -->
          <div class="flex flex-wrap items-center gap-2">
            <input
              v-model="themeName"
              :placeholder="t('klipperscreenStudio.themes.namePlaceholder')"
              class="min-w-[8rem] flex-1 rounded-brutal border-3 border-ink bg-paper px-2 py-1 text-xs"
            />
            <button
              class="nb-btn bg-brand-lime px-3 py-1 text-xs"
              :disabled="themesBusy || !themeName.trim()"
              @click="createAndApply(true)"
            >
              {{ t('klipperscreenStudio.themes.createApply') }}
            </button>
            <button
              class="nb-btn bg-surface px-3 py-1 text-xs"
              :disabled="themesBusy || !themeName.trim()"
              @click="createAndApply(false)"
            >
              {{ t('klipperscreenStudio.themes.createOnly') }}
            </button>
          </div>

          <!-- installed themes -->
          <div v-if="themes.length" class="space-y-1">
            <p class="text-xs font-bold">{{ t('klipperscreenStudio.themes.installed') }}</p>
            <ul class="space-y-1">
              <li v-for="th in themes" :key="th.name" class="flex items-center gap-2 text-[11px]">
                <span class="min-w-0 flex-1 truncate font-mono"
                  >{{ th.name
                  }}<span
                    v-if="th.generated"
                    class="ms-1 opacity-50"
                    :title="t('klipperscreenStudio.themes.generated')"
                    >★</span
                  ></span
                >
                <button
                  class="nb-btn shrink-0 bg-surface px-2 py-0.5"
                  :disabled="themesBusy"
                  @click="applyExisting(th.name)"
                >
                  {{ t('klipperscreenStudio.themes.apply') }}
                </button>
                <button
                  v-if="th.generated"
                  class="nb-btn shrink-0 bg-surface px-2 py-0.5"
                  :disabled="themesBusy"
                  :aria-label="t('klipperscreenStudio.themes.delete')"
                  @click="removeTheme(th.name)"
                >
                  ✕
                </button>
              </li>
            </ul>
          </div>

          <p
            v-if="themesNote"
            class="nb-card flex flex-wrap items-center gap-2 bg-brand-lime/20 p-2 text-[11px]"
          >
            <span class="min-w-0 flex-1">{{ themesNote }}</span>
            <button
              class="nb-btn shrink-0 bg-brand-yellow px-2 py-0.5"
              :disabled="restarting"
              @click="doRestart"
            >
              {{
                restarting
                  ? t('klipperscreenStudio.restart.restarting')
                  : t('klipperscreenStudio.restart.button')
              }}
            </button>
          </p>
          <p v-if="restarted" class="text-[11px] font-bold text-brand-lime">
            ✓ {{ t('klipperscreenStudio.restart.done') }}
          </p>
          <p
            v-if="themesError"
            role="alert"
            class="nb-card bg-brand-red/10 p-2 font-mono text-[11px]"
          >
            {{ themesError }}
          </p>
          <p
            v-if="restartError"
            role="alert"
            class="nb-card bg-brand-red/10 p-2 font-mono text-[11px]"
          >
            {{ restartError }}
          </p>
        </template>
      </template>
    </template>
  </div>
</template>
