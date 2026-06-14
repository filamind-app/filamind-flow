<script setup lang="ts">
/** KlipperScreen Studio — edit the touchscreen's config and restart it to apply.
 *
 *  Phase 1: a safe raw editor for `KlipperScreen.conf` (gated save = timestamped backup +
 *  stale-write guard + refused while printing, reusing the Config Editor's machinery) plus a
 *  one-tap service restart. The graphical option editor + theme builder build on this. */
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import HelpDrawer from '@/components/ui/HelpDrawer.vue'
import { describeError } from '@/core/describeError'

import { GLOSSARY_KEYS, HELP_ILLO, HELP_TOPICS } from './help'
import HelpIllo from './HelpIllo.vue'
import {
  activateTheme,
  createTheme,
  deleteTheme,
  fetchKioskStatus,
  fetchMenus,
  fetchScreenConf,
  fetchScreenOptions,
  fetchScreenStatus,
  fetchThemes,
  type KioskStatus,
  type MenuItem,
  restartScreen,
  restoreScreen,
  saveMenus,
  saveScreenConf,
  saveScreenOptions,
  ScreenSaveError,
  type ScreenTheme,
  switchToKiosk,
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
type View = 'config' | 'settings' | 'menus' | 'themes' | 'kiosk'
const view = ref<View>('config')
const themes = ref<ScreenTheme[]>([])
const tokens = ref<string[]>([])
const palette = reactive<Record<string, string>>({})
const radius = ref(8)
const themeName = ref('')
const themesBusy = ref(false)
const themesError = ref<string | null>(null)
const themesNote = ref<string | null>(null)

// Menu tree editor
const menuItems = ref<MenuItem[]>([])
const panels = ref<string[]>([])
const menuSha = ref<string | null>(null)
const menusBusy = ref(false)
const menusError = ref<string | null>(null)
const menusNote = ref<string | null>(null)
const menusDirty = ref(false)
const selectedMenuId = ref<string | null>(null)
const MENU_TREES = ['__main', '__print', '__splashscreen']
let menuSeq = 0

// FilaMind Kiosk — reversible swap of the touchscreen
const kiosk = ref<KioskStatus | null>(null)
const kioskBusy = ref(false)
const kioskError = ref<string | null>(null)
const kioskNote = ref<string | null>(null)
const kioskPersist = ref(false)
const confirmKiosk = ref<null | 'switch' | 'restore'>(null)

// Settings — friendly form over the common [main] options
type SettingField = { key: string; type: 'bool' | 'select'; options?: string[] }
const SETTINGS_FIELDS: SettingField[] = [
  { key: 'theme', type: 'select' }, // options filled from installed themes
  { key: 'language', type: 'select', options: ['', 'en', 'de', 'es', 'fr', 'ru', 'zh_CN'] },
  {
    key: 'screen_blanking',
    type: 'select',
    options: ['off', '30', '60', '120', '300', '600', '1800', '3600', '14400'],
  },
  { key: 'font_size', type: 'select', options: ['small', 'medium', 'large', 'max'] },
  { key: '24htime', type: 'bool' },
  { key: 'use_dpms', type: 'bool' },
  { key: 'show_cursor', type: 'bool' },
  { key: 'confirm_estop', type: 'bool' },
  { key: 'show_heater_power', type: 'bool' },
  { key: 'autoclose_popups', type: 'bool' },
]
const settingsLoaded = ref<Record<string, string>>({})
const settingsValues = reactive<Record<string, string>>({})
const settingsSha = ref<string | null>(null)
const settingsTouched = reactive(new Set<string>())
const settingsBusy = ref(false)
const settingsError = ref<string | null>(null)
const settingsSaved = ref(false)

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
  if (v === 'menus' && !menuItems.value.length && !menuSha.value) void loadMenus()
  if (v === 'kiosk' && !kiosk.value) void loadKiosk()
  if (v === 'settings' && !Object.keys(settingsValues).length) void loadSettings()
}

async function loadKiosk(): Promise<void> {
  kioskBusy.value = true
  kioskError.value = null
  try {
    kiosk.value = await fetchKioskStatus()
  } catch (e) {
    kioskError.value = describeError(e)
  } finally {
    kioskBusy.value = false
  }
}

async function doKiosk(action: 'switch' | 'restore'): Promise<void> {
  confirmKiosk.value = null
  kioskBusy.value = true
  kioskError.value = null
  kioskNote.value = null
  try {
    kiosk.value =
      action === 'switch'
        ? await switchToKiosk(kioskPersist.value)
        : await restoreScreen(kioskPersist.value)
    kioskNote.value = t(
      action === 'switch'
        ? 'klipperscreenStudio.kiosk.switchedNote'
        : 'klipperscreenStudio.kiosk.restoredNote',
    )
  } catch (e) {
    kioskError.value = describeError(e)
  } finally {
    kioskBusy.value = false
  }
}

const themeOptions = computed(() => themes.value.map((th) => th.name))

/** The selectable values for a settings field — always offers "unset" + the current value. */
function settingOptions(f: SettingField): string[] {
  let opts = f.key === 'theme' ? themeOptions.value : (f.options ?? [])
  if (!opts.includes('')) opts = ['', ...opts]
  const cur = settingsValues[f.key]
  if (cur && !opts.includes(cur)) opts = [...opts, cur]
  return opts
}

/** A human label for an option value (seconds → 30 s / 5 min / 1 h, font sizes, "unset"). */
function settingOptionLabel(key: string, v: string): string {
  if (v === '') return t('klipperscreenStudio.settings.unset')
  if (key === 'screen_blanking') {
    if (v === 'off') return t('klipperscreenStudio.settings.never')
    const n = Number(v)
    if (!Number.isFinite(n)) return v
    if (n >= 3600) return `${n / 3600} h`
    if (n >= 60) return `${n / 60} min`
    return `${n} s`
  }
  if (key === 'font_size') return t('klipperscreenStudio.settings.fontSize.' + v)
  return v
}

async function loadSettings(): Promise<void> {
  settingsBusy.value = true
  settingsError.value = null
  try {
    const s = await fetchScreenOptions()
    settingsLoaded.value = s.options
    settingsSha.value = s.sha256
    settingsTouched.clear()
    for (const f of SETTINGS_FIELDS) settingsValues[f.key] = s.options[f.key] ?? ''
    if (!themes.value.length) await loadThemes() // populate the theme dropdown
  } catch (e) {
    settingsError.value = describeError(e)
  } finally {
    settingsBusy.value = false
  }
}

function onSetting(key: string, value: string): void {
  settingsValues[key] = value
  settingsTouched.add(key)
  settingsSaved.value = false
}

async function saveSettings(): Promise<void> {
  const changed: Record<string, string> = {}
  for (const k of settingsTouched) changed[k] = settingsValues[k]
  if (!Object.keys(changed).length) return
  settingsBusy.value = true
  settingsError.value = null
  try {
    const c = await saveScreenOptions(changed, settingsSha.value)
    settingsSha.value = c.sha256
    settingsLoaded.value = { ...settingsLoaded.value, ...changed }
    settingsTouched.clear()
    settingsSaved.value = true
  } catch (e) {
    if (e instanceof ScreenSaveError && e.status === 412)
      settingsError.value = t('klipperscreenStudio.save.stale')
    else if (e instanceof ScreenSaveError && e.status === 409)
      settingsError.value = t('klipperscreenStudio.save.busy')
    else settingsError.value = describeError(e)
  } finally {
    settingsBusy.value = false
  }
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

async function loadMenus(): Promise<void> {
  menusBusy.value = true
  menusError.value = null
  try {
    const cat = await fetchMenus()
    menuItems.value = cat.items
    panels.value = cat.panels
    menuSha.value = cat.sha256
    menusDirty.value = false
  } catch (e) {
    menusError.value = describeError(e)
  } finally {
    menusBusy.value = false
  }
}

/** The menu trees (the standard three + any present), each as a DFS-ordered row list with depth. */
const menuTrees = computed(() => {
  const trees = new Set<string>(MENU_TREES)
  for (const it of menuItems.value) trees.add(it.tree)
  const byParent: Record<string, MenuItem[]> = {}
  for (const it of menuItems.value) (byParent[it.parent] ??= []).push(it)
  return [...trees].map((tree) => {
    const rows: { item: MenuItem; depth: number }[] = []
    const walk = (parent: string, depth: number): void => {
      for (const it of byParent[parent] ?? []) {
        rows.push({ item: it, depth })
        walk(it.id, depth + 1)
      }
    }
    walk(tree, 0)
    return { tree, rows }
  })
})

function addMenuItem(parent: string, tree: string): void {
  const existing = new Set(menuItems.value.map((i) => i.id))
  let token = ''
  do {
    menuSeq += 1
    token = `item${menuSeq}`
  } while (existing.has(`${parent} ${token}`))
  const item: MenuItem = {
    id: `${parent} ${token}`,
    tree,
    parent,
    props: { name: t('klipperscreenStudio.menus.newItem') },
  }
  menuItems.value.push(item)
  selectedMenuId.value = item.id
  menusDirty.value = true
}

function removeMenuItem(item: MenuItem): void {
  const prefix = item.id + ' '
  menuItems.value = menuItems.value.filter((i) => i.id !== item.id && !i.id.startsWith(prefix))
  if (selectedMenuId.value === item.id) selectedMenuId.value = null
  menusDirty.value = true
}

function moveMenuItem(item: MenuItem, dir: -1 | 1): void {
  const sibs = menuItems.value.filter((i) => i.parent === item.parent)
  const swapWith = sibs[sibs.indexOf(item) + dir]
  if (!swapWith) return
  const arr = menuItems.value
  const a = arr.indexOf(item)
  const b = arr.indexOf(swapWith)
  ;[arr[a], arr[b]] = [arr[b], arr[a]]
  menusDirty.value = true
}

function menuActionType(it: MenuItem): 'panel' | 'gcode' | 'submenu' {
  if (it.props.panel) return 'panel'
  if (it.props.method) return 'gcode'
  return 'submenu'
}

function setMenuActionType(it: MenuItem, type: string): void {
  delete it.props.panel
  delete it.props.method
  delete it.props.params
  if (type === 'panel') it.props.panel = panels.value[0] ?? 'move'
  else if (type === 'gcode') {
    it.props.method = 'printer.gcode.script'
    it.props.params = '{"script": "G28"}'
  }
  menusDirty.value = true
}

function menuGcode(it: MenuItem): string {
  try {
    return String((JSON.parse(it.props.params || '{}') as { script?: string }).script ?? '')
  } catch {
    return it.props.params ?? ''
  }
}

function setMenuGcode(it: MenuItem, script: string): void {
  it.props.method = 'printer.gcode.script'
  it.props.params = JSON.stringify({ script })
  menusDirty.value = true
}

async function saveMenusHandler(): Promise<void> {
  menusBusy.value = true
  menusError.value = null
  menusNote.value = null
  try {
    const payload = menuItems.value.map((i) => ({ id: i.id, props: { ...i.props } }))
    const c = await saveMenus(payload, menuSha.value)
    menuSha.value = c.sha256
    menusDirty.value = false
    menusNote.value = t('klipperscreenStudio.menus.savedRestart')
  } catch (e) {
    if (e instanceof ScreenSaveError && e.status === 412)
      menusError.value = t('klipperscreenStudio.save.stale')
    else if (e instanceof ScreenSaveError && e.status === 409)
      menusError.value = t('klipperscreenStudio.save.busy')
    else menusError.value = describeError(e)
  } finally {
    menusBusy.value = false
  }
}

onMounted(() => void loadStatus())
</script>

<template>
  <div class="space-y-3 text-sm">
    <div class="flex items-start justify-between gap-2">
      <p class="min-w-0 flex-1 text-xs opacity-70">{{ t('klipperscreenStudio.intro') }}</p>
      <HelpDrawer
        class="shrink-0"
        namespace="klipperscreenStudio"
        :topics="HELP_TOPICS"
        :illo-map="HELP_ILLO"
        :illo="HelpIllo"
        :glossary-keys="GLOSSARY_KEYS"
        steps-key="klipperscreenStudio.help.steps"
        :button-label="t('klipperscreenStudio.help.guide')"
        :title="t('klipperscreenStudio.help.guideTitle')"
        :close-label="t('klipperscreenStudio.help.close')"
        :steps-title="t('klipperscreenStudio.help.howToRead')"
      />
    </div>

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

      <!-- Config / Settings / Menus / Themes / Kiosk view toggle -->
      <div class="-mx-1 overflow-x-auto px-1">
        <div class="inline-flex overflow-hidden rounded-brutal border-2 border-ink" role="group">
          <button
            v-for="v in ['config', 'settings', 'menus', 'themes', 'kiosk'] as const"
            :key="v"
            type="button"
            class="nb-seg whitespace-nowrap"
            :class="view === v ? 'bg-ink text-surface' : 'bg-surface text-ink hover:bg-brand-cyan'"
            :aria-pressed="view === v"
            @click="switchView(v)"
          >
            {{ t('klipperscreenStudio.view.' + v) }}
          </button>
        </div>
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

      <!-- Settings view: a friendly form over the common [main] options -->
      <template v-else-if="view === 'settings'">
        <p
          v-if="settingsBusy && !Object.keys(settingsValues).length"
          class="font-mono text-xs opacity-70"
        >
          {{ t('klipperscreenStudio.settings.loading') }}
        </p>
        <template v-else>
          <p class="text-[11px] opacity-70">{{ t('klipperscreenStudio.settings.intro') }}</p>

          <div class="nb-card space-y-2 bg-surface p-3">
            <div
              v-for="f in SETTINGS_FIELDS"
              :key="f.key"
              class="flex flex-wrap items-center gap-x-3 gap-y-1"
            >
              <label v-if="f.type === 'bool'" class="flex items-center gap-2 text-xs">
                <input
                  type="checkbox"
                  class="h-4 w-4"
                  :checked="settingsValues[f.key] === 'True'"
                  @change="
                    onSetting(f.key, ($event.target as HTMLInputElement).checked ? 'True' : 'False')
                  "
                />
                <span class="font-medium">{{
                  t('klipperscreenStudio.settings.label.' + f.key)
                }}</span>
              </label>
              <template v-else>
                <label :for="'set-' + f.key" class="min-w-[8rem] text-xs font-medium">
                  {{ t('klipperscreenStudio.settings.label.' + f.key) }}
                </label>
                <select
                  :id="'set-' + f.key"
                  class="min-w-0 flex-1 rounded-brutal border-2 border-ink bg-paper px-2 py-1 text-xs"
                  :value="settingsValues[f.key]"
                  @change="onSetting(f.key, ($event.target as HTMLSelectElement).value)"
                >
                  <option v-for="opt in settingOptions(f)" :key="opt" :value="opt">
                    {{ settingOptionLabel(f.key, opt) }}
                  </option>
                </select>
              </template>
            </div>
          </div>

          <p class="text-[11px] opacity-60">{{ t('klipperscreenStudio.settings.onlyChanged') }}</p>

          <button
            class="nb-btn bg-brand-lime px-3 py-1 text-xs"
            :disabled="settingsBusy || !settingsTouched.size"
            @click="saveSettings"
          >
            {{
              settingsBusy
                ? t('klipperscreenStudio.editor.saving')
                : t('klipperscreenStudio.settings.save')
            }}
          </button>

          <p
            v-if="settingsSaved"
            class="nb-card flex flex-wrap items-center gap-2 bg-brand-lime/20 p-2 text-[11px]"
          >
            <span class="min-w-0 flex-1">{{ t('klipperscreenStudio.settings.savedRestart') }}</span>
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
            v-if="settingsError"
            role="alert"
            class="nb-card bg-brand-red/10 p-2 font-mono text-[11px]"
          >
            {{ settingsError }}
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

      <!-- Menus view: design the on-screen menu tree (what's on each screen + what it does) -->
      <template v-else-if="view === 'menus'">
        <p v-if="menusBusy && !menuItems.length && !menuSha" class="font-mono text-xs opacity-70">
          {{ t('klipperscreenStudio.menus.loading') }}
        </p>
        <template v-else>
          <p class="text-[11px] opacity-70">{{ t('klipperscreenStudio.menus.intro') }}</p>

          <div v-for="grp in menuTrees" :key="grp.tree" class="nb-card space-y-1 bg-surface p-2">
            <div class="flex items-center justify-between gap-2">
              <span class="font-mono text-[11px] font-bold">{{ grp.tree }}</span>
              <button
                class="nb-btn bg-surface px-2 py-0.5 text-[11px]"
                @click="addMenuItem(grp.tree, grp.tree)"
              >
                + {{ t('klipperscreenStudio.menus.addItem') }}
              </button>
            </div>
            <p v-if="!grp.rows.length" class="text-[11px] opacity-50">
              {{ t('klipperscreenStudio.menus.empty') }}
            </p>
            <template v-for="row in grp.rows" :key="row.item.id">
              <div
                class="flex items-center gap-1 rounded px-1 py-0.5 text-[11px]"
                :class="selectedMenuId === row.item.id ? 'bg-brand-cyan/30' : 'hover:bg-ink/5'"
                :style="{ marginInlineStart: row.depth * 14 + 'px' }"
              >
                <button
                  class="min-w-0 flex-1 truncate text-start"
                  @click="selectedMenuId = selectedMenuId === row.item.id ? null : row.item.id"
                >
                  <span class="font-bold">{{
                    row.item.props.name || row.item.id.split(' ').pop()
                  }}</span>
                  <span class="ms-1 opacity-50">{{
                    menuActionType(row.item) === 'panel'
                      ? '▸ ' + row.item.props.panel
                      : menuActionType(row.item) === 'gcode'
                        ? '⌨'
                        : '📁'
                  }}</span>
                </button>
                <button
                  class="shrink-0 px-1 opacity-60 hover:opacity-100"
                  :aria-label="t('klipperscreenStudio.menus.up')"
                  @click="moveMenuItem(row.item, -1)"
                >
                  ▲
                </button>
                <button
                  class="shrink-0 px-1 opacity-60 hover:opacity-100"
                  :aria-label="t('klipperscreenStudio.menus.down')"
                  @click="moveMenuItem(row.item, 1)"
                >
                  ▼
                </button>
                <button
                  class="shrink-0 px-1 opacity-60 hover:opacity-100"
                  :aria-label="t('klipperscreenStudio.menus.addChild')"
                  @click="addMenuItem(row.item.id, grp.tree)"
                >
                  ＋
                </button>
                <button
                  class="shrink-0 px-1 text-brand-red opacity-70 hover:opacity-100"
                  :aria-label="t('klipperscreenStudio.menus.delete')"
                  @click="removeMenuItem(row.item)"
                >
                  ✕
                </button>
              </div>

              <div
                v-if="selectedMenuId === row.item.id"
                class="space-y-1.5 rounded-brutal border-2 border-ink bg-paper p-2 text-[11px]"
                :style="{ marginInlineStart: row.depth * 14 + 12 + 'px' }"
              >
                <label class="flex items-center gap-2">
                  <span class="w-16 shrink-0 opacity-60">{{
                    t('klipperscreenStudio.menus.name')
                  }}</span>
                  <input
                    v-model="row.item.props.name"
                    class="min-w-0 flex-1 rounded border-2 border-ink bg-surface px-1.5 py-0.5"
                    @input="menusDirty = true"
                  />
                </label>
                <label class="flex items-center gap-2">
                  <span class="w-16 shrink-0 opacity-60">{{
                    t('klipperscreenStudio.menus.icon')
                  }}</span>
                  <input
                    v-model="row.item.props.icon"
                    placeholder="home"
                    class="min-w-0 flex-1 rounded border-2 border-ink bg-surface px-1.5 py-0.5 font-mono"
                    @input="menusDirty = true"
                  />
                </label>
                <label class="flex items-center gap-2">
                  <span class="w-16 shrink-0 opacity-60">{{
                    t('klipperscreenStudio.menus.action')
                  }}</span>
                  <select
                    :value="menuActionType(row.item)"
                    class="min-w-0 flex-1 rounded border-2 border-ink bg-surface px-1.5 py-0.5"
                    @change="
                      setMenuActionType(row.item, ($event.target as HTMLSelectElement).value)
                    "
                  >
                    <option value="submenu">{{ t('klipperscreenStudio.menus.actSubmenu') }}</option>
                    <option value="panel">{{ t('klipperscreenStudio.menus.actPanel') }}</option>
                    <option value="gcode">{{ t('klipperscreenStudio.menus.actGcode') }}</option>
                  </select>
                </label>
                <label v-if="menuActionType(row.item) === 'panel'" class="flex items-center gap-2">
                  <span class="w-16 shrink-0 opacity-60">{{
                    t('klipperscreenStudio.menus.panel')
                  }}</span>
                  <select
                    v-model="row.item.props.panel"
                    class="min-w-0 flex-1 rounded border-2 border-ink bg-surface px-1.5 py-0.5 font-mono"
                    @change="menusDirty = true"
                  >
                    <option v-for="p in panels" :key="p" :value="p">{{ p }}</option>
                  </select>
                </label>
                <label
                  v-else-if="menuActionType(row.item) === 'gcode'"
                  class="flex items-center gap-2"
                >
                  <span class="w-16 shrink-0 opacity-60">{{
                    t('klipperscreenStudio.menus.gcode')
                  }}</span>
                  <input
                    :value="menuGcode(row.item)"
                    placeholder="G28"
                    class="min-w-0 flex-1 rounded border-2 border-ink bg-surface px-1.5 py-0.5 font-mono"
                    @input="setMenuGcode(row.item, ($event.target as HTMLInputElement).value)"
                  />
                </label>
                <label class="flex items-center gap-2">
                  <span class="w-16 shrink-0 opacity-60">{{
                    t('klipperscreenStudio.menus.enable')
                  }}</span>
                  <input
                    v-model="row.item.props.enable"
                    :placeholder="'{{ printer.extruders.count > 0 }}'"
                    class="min-w-0 flex-1 rounded border-2 border-ink bg-surface px-1.5 py-0.5 font-mono"
                    @input="menusDirty = true"
                  />
                </label>
              </div>
            </template>
          </div>

          <div class="flex flex-wrap items-center gap-2">
            <button
              class="nb-btn bg-brand-lime px-3 py-1 text-xs"
              :disabled="menusBusy || !menusDirty"
              @click="saveMenusHandler"
            >
              {{
                menusBusy
                  ? t('klipperscreenStudio.editor.saving')
                  : t('klipperscreenStudio.menus.save')
              }}
            </button>
            <span v-if="menusDirty" class="text-[11px] opacity-60">{{
              t('klipperscreenStudio.editor.unsaved')
            }}</span>
          </div>
          <p
            v-if="menusNote"
            class="nb-card flex flex-wrap items-center gap-2 bg-brand-lime/20 p-2 text-[11px]"
          >
            <span class="min-w-0 flex-1">{{ menusNote }}</span>
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
            v-if="menusError"
            role="alert"
            class="nb-card bg-brand-red/10 p-2 font-mono text-[11px]"
          >
            {{ menusError }}
          </p>
        </template>
      </template>

      <!-- Themes view: palette pickers + live preview + theme management -->
      <template v-else-if="view === 'themes'">
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

      <!-- Kiosk view: turn the touchscreen into FilaMind itself (reversible swap) -->
      <template v-else-if="view === 'kiosk'">
        <p v-if="kioskBusy && !kiosk" class="font-mono text-xs opacity-70">
          {{ t('klipperscreenStudio.kiosk.loading') }}
        </p>
        <template v-else>
          <p class="text-[11px] opacity-70">{{ t('klipperscreenStudio.kiosk.intro') }}</p>

          <!-- current screen mode -->
          <div
            class="nb-card flex flex-wrap items-center gap-x-3 gap-y-1 bg-surface p-3 text-[11px]"
          >
            <span class="font-bold uppercase tracking-wide opacity-60">{{
              t('klipperscreenStudio.kiosk.current')
            }}</span>
            <span
              class="nb-badge"
              :class="kiosk?.mode === 'kiosk' ? 'bg-brand-lime' : 'bg-brand-cyan'"
            >
              {{ t('klipperscreenStudio.kiosk.mode.' + (kiosk?.mode ?? 'none')) }}
            </span>
            <span v-if="kiosk?.url" class="font-mono opacity-70">{{ kiosk.url }}</span>
          </div>

          <!-- not installed yet: how to provision -->
          <div
            v-if="kiosk && !kiosk.kiosk_installed"
            class="nb-card space-y-1 bg-brand-yellow/15 p-3 text-[11px]"
          >
            <p class="font-bold">{{ t('klipperscreenStudio.kiosk.notInstalled') }}</p>
            <p class="opacity-80">{{ t('klipperscreenStudio.kiosk.setupHint') }}</p>
            <code class="block rounded bg-ink/5 p-1.5 font-mono"
              >cd ~/filamind-flow && sudo bash scripts/install.sh kiosk</code
            >
          </div>

          <!-- installed: the reversible toggle -->
          <template v-else-if="kiosk">
            <label class="flex items-center gap-2 text-[11px]">
              <input v-model="kioskPersist" type="checkbox" class="h-4 w-4" />
              <span>{{ t('klipperscreenStudio.kiosk.persist') }}</span>
            </label>
            <p class="text-[11px] opacity-60">{{ t('klipperscreenStudio.kiosk.safety') }}</p>

            <div class="flex flex-wrap items-center gap-2">
              <button
                v-if="kiosk.mode !== 'kiosk'"
                class="nb-btn bg-brand-lime px-3 py-1 text-xs"
                :disabled="kioskBusy"
                @click="confirmKiosk = 'switch'"
              >
                {{ t('klipperscreenStudio.kiosk.switchBtn') }}
              </button>
              <button
                v-if="kiosk.mode === 'kiosk' || !kiosk.screen_active"
                class="nb-btn bg-surface px-3 py-1 text-xs"
                :disabled="kioskBusy"
                @click="confirmKiosk = 'restore'"
              >
                {{ t('klipperscreenStudio.kiosk.restoreBtn') }}
              </button>
              <span class="flex-1"></span>
              <button
                class="nb-btn bg-surface px-2 py-0.5 text-[11px]"
                :disabled="kioskBusy"
                @click="loadKiosk"
              >
                ↻ {{ t('klipperscreenStudio.kiosk.refresh') }}
              </button>
            </div>

            <!-- confirm -->
            <div
              v-if="confirmKiosk"
              class="nb-card space-y-2 border-brand-red bg-brand-yellow/20 p-2"
            >
              <p class="text-xs font-bold">
                {{
                  t(
                    confirmKiosk === 'switch'
                      ? 'klipperscreenStudio.kiosk.confirmSwitchTitle'
                      : 'klipperscreenStudio.kiosk.confirmRestoreTitle',
                  )
                }}
              </p>
              <p class="text-[11px] opacity-80">{{ t('klipperscreenStudio.kiosk.confirmBody') }}</p>
              <div class="flex gap-2">
                <button
                  class="nb-btn bg-brand-red px-3 py-1 text-xs text-paper"
                  @click="confirmKiosk && doKiosk(confirmKiosk)"
                >
                  {{ t('klipperscreenStudio.kiosk.confirm') }}
                </button>
                <button class="nb-btn bg-surface px-3 py-1 text-xs" @click="confirmKiosk = null">
                  {{ t('klipperscreenStudio.kiosk.cancel') }}
                </button>
              </div>
            </div>
          </template>

          <p v-if="kioskNote" class="text-[11px] font-bold text-brand-lime">✓ {{ kioskNote }}</p>
          <p
            v-if="kioskError"
            role="alert"
            class="nb-card bg-brand-red/10 p-2 font-mono text-[11px]"
          >
            {{ kioskError }}
          </p>
        </template>
      </template>
    </template>
  </div>
</template>
