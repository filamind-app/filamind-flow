<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import {
  buildFirmware,
  deleteProfile,
  downloadArtifact,
  duplicateProfile,
  fetchConfigTree,
  fetchProfiles,
  renameProfile,
  saveProfile,
} from './api'
import type { ConfigNode, FirmwareProfile } from './types'

const { t } = useI18n({ useScope: 'global' })

defineEmits<{ close: [] }>()

const profiles = ref<FirmwareProfile[]>([])
const baseProfile = ref<string | null>(null)
const tree = ref<ConfigNode[]>([])
const edits = ref<Record<string, string>>({})
const showOptional = ref(false)
const showHelp = ref(false)
const showRaw = ref(false)

const loading = ref(true)
const saving = ref(false)
const building = ref(false)
const buildLog = ref('')
const error = ref<string | null>(null)
const message = ref<string | null>(null)
const profileName = ref('')
const manageName = ref('')

const selectedProfile = computed(
  () => profiles.value.find((p) => p.name === baseProfile.value) ?? null,
)
const selectedBuilt = computed(() => selectedProfile.value?.built ?? false)

const inputClass =
  'shrink-0 max-w-[55%] rounded-brutal border-2 border-ink bg-surface px-2 py-0.5 text-xs'

interface FlatNode {
  node: ConfigNode
  depth: number
}

function flatten(nodes: ConfigNode[], depth = 0, acc: FlatNode[] = []): FlatNode[] {
  for (const node of nodes) {
    acc.push({ node, depth })
    if (node.children.length) flatten(node.children, depth + 1, acc)
  }
  return acc
}

const flat = computed(() => flatten(tree.value))
const dirtyCount = computed(() => Object.keys(edits.value).length)

function editList(): { name: string; value: string }[] {
  return Object.entries(edits.value).map(([name, value]) => ({ name, value }))
}

async function reloadTree(): Promise<void> {
  error.value = null
  try {
    tree.value = await fetchConfigTree({
      profile: baseProfile.value,
      values: editList(),
      show_optional: showOptional.value,
    })
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('firmware.configEditor.errLoad')
  } finally {
    loading.value = false
  }
}

async function loadProfiles(): Promise<void> {
  try {
    profiles.value = (await fetchProfiles()).profiles
  } catch {
    /* profiles are optional context; ignore */
  }
}

function selectProfile(): void {
  edits.value = {}
  loading.value = true
  void reloadTree()
}

function boolOn(node: ConfigNode): boolean {
  return node.value === 'y'
}

/** A bool/tristate row whose whole width is a click target to toggle. */
function isToggle(node: ConfigNode): boolean {
  return node.type === 'bool' || node.type === 'tristate'
}

function toggleBool(node: ConfigNode): void {
  if (node.readonly) return
  edits.value[node.name] = boolOn(node) ? 'n' : 'y'
  void reloadTree()
}

function onSelect(node: ConfigNode, event: Event): void {
  const value = (event.target as HTMLSelectElement).value
  for (const choice of node.choices) delete edits.value[choice.name]
  edits.value[value] = 'y'
  void reloadTree()
}

function onInput(node: ConfigNode, event: Event): void {
  edits.value[node.name] = (event.target as HTMLInputElement).value
  void reloadTree()
}

async function save(): Promise<void> {
  saving.value = true
  error.value = null
  message.value = null
  try {
    await saveProfile({
      name: profileName.value.trim(),
      values: editList(),
      base_profile: baseProfile.value,
    })
    message.value = t('firmware.configEditor.savedProfile', { name: profileName.value.trim() })
    baseProfile.value = profileName.value.trim()
    edits.value = {}
    profileName.value = ''
    await loadProfiles()
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('firmware.configEditor.errSave')
  } finally {
    saving.value = false
  }
}

async function downloadBin(): Promise<void> {
  if (!baseProfile.value) return
  error.value = null
  try {
    await downloadArtifact(baseProfile.value)
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('firmware.configEditor.errDownload')
  }
}

async function removeProfile(name: string): Promise<void> {
  try {
    await deleteProfile(name)
    if (baseProfile.value === name) baseProfile.value = null
    await loadProfiles()
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('firmware.configEditor.errDelete')
  }
}

async function renameSelected(): Promise<void> {
  const target = manageName.value.trim()
  if (!baseProfile.value || !target) return
  error.value = null
  message.value = null
  try {
    await renameProfile(baseProfile.value, target)
    message.value = t('firmware.configEditor.renamedTo', { name: target })
    baseProfile.value = target
    manageName.value = ''
    await loadProfiles()
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('firmware.configEditor.errRename')
  }
}

async function duplicateSelected(): Promise<void> {
  const target = manageName.value.trim()
  if (!baseProfile.value || !target) return
  error.value = null
  message.value = null
  try {
    await duplicateProfile(baseProfile.value, target)
    message.value = t('firmware.configEditor.duplicatedTo', { name: target })
    baseProfile.value = target
    edits.value = {}
    manageName.value = ''
    await loadProfiles()
    await reloadTree()
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('firmware.configEditor.errDuplicate')
  }
}

async function build(): Promise<void> {
  if (!baseProfile.value || building.value) return
  building.value = true
  buildLog.value = ''
  try {
    // Auto-save pending edits into the profile so the build reflects them.
    if (dirtyCount.value > 0) {
      // Build-log lines are technical console output — kept English (not externalized).
      buildLog.value += `>>> saving ${dirtyCount.value} pending edit(s) to ${baseProfile.value}…\n`
      await saveProfile({
        name: baseProfile.value,
        values: editList(),
        base_profile: baseProfile.value,
      })
      edits.value = {}
    }
    buildLog.value += `>>> compiling ${baseProfile.value}…\n`
    await buildFirmware(baseProfile.value, (chunk) => {
      buildLog.value += chunk
    })
    await loadProfiles()
  } catch (e) {
    buildLog.value += `\n!! ${e instanceof Error ? e.message : 'build failed'}\n`
  } finally {
    building.value = false
  }
}

onMounted(async () => {
  await Promise.all([loadProfiles(), reloadTree()])
})
</script>

<template>
  <div class="space-y-2 text-sm">
    <div class="flex items-center justify-between gap-2">
      <span class="text-xs font-bold uppercase tracking-wide">{{
        t('firmware.configEditor.title')
      }}</span>
      <button class="nb-btn px-2 py-0.5 text-xs" @click="$emit('close')">
        {{ t('firmware.configEditor.back') }}
      </button>
    </div>

    <div class="flex flex-wrap items-center gap-2 rounded-brutal border-2 border-ink p-2">
      <select v-model="baseProfile" :class="['flex-1', inputClass]" @change="selectProfile">
        <option :value="null">{{ t('firmware.configEditor.blankConfig') }}</option>
        <option v-for="p in profiles" :key="p.name" :value="p.name">{{ p.name }}</option>
      </select>
      <label class="flex items-center gap-1 text-[11px]">
        <input v-model="showOptional" type="checkbox" @change="reloadTree" />
        {{ t('firmware.configEditor.optional') }}
      </label>
      <label
        class="flex items-center gap-1 text-[11px]"
        :title="t('firmware.configEditor.optionDocsTitle')"
      >
        <input v-model="showHelp" type="checkbox" /> {{ t('firmware.configEditor.optionDocs') }}
      </label>
      <label
        class="flex items-center gap-1 text-[11px]"
        :title="t('firmware.configEditor.rawTitle')"
      >
        <input v-model="showRaw" type="checkbox" /> {{ t('firmware.configEditor.raw') }}
      </label>
      <span v-if="dirtyCount" class="nb-badge bg-brand-yellow text-[11px]">{{
        t('firmware.configEditor.editsBadge', { n: dirtyCount }, dirtyCount)
      }}</span>
      <span v-if="selectedBuilt" class="nb-badge bg-brand-lime text-[11px]">{{
        t('firmware.configEditor.builtBadge')
      }}</span>
      <button
        v-if="baseProfile"
        class="nb-btn bg-brand-cyan px-2 py-0.5 text-[11px]"
        :disabled="building"
        :title="
          dirtyCount
            ? t('firmware.configEditor.buildTitleDirty')
            : t('firmware.configEditor.buildTitle')
        "
        @click="build"
      >
        {{
          building ? t('firmware.configEditor.building') : t('firmware.configEditor.buildProfile')
        }}
      </button>
      <button
        v-if="selectedBuilt"
        class="nb-btn bg-brand-lime px-2 py-0.5 text-[11px]"
        :title="t('firmware.configEditor.downloadBinTitle')"
        @click="downloadBin"
      >
        {{ t('firmware.configEditor.downloadBin') }}
      </button>
      <button
        v-if="baseProfile"
        class="nb-btn bg-brand-red px-2 py-0.5 text-[11px] text-surface"
        @click="removeProfile(baseProfile)"
      >
        {{ t('firmware.configEditor.delete') }}
      </button>
    </div>

    <div
      v-if="baseProfile"
      class="flex flex-wrap items-center gap-2 rounded-brutal border-2 border-ink px-2 py-1"
    >
      <span class="text-[11px] font-bold uppercase opacity-70">{{
        t('firmware.configEditor.manage')
      }}</span>
      <input
        v-model="manageName"
        :placeholder="t('firmware.configEditor.newNamePlaceholder')"
        :class="[inputClass, 'max-w-none flex-1']"
        @keyup.enter="renameSelected"
      />
      <button
        class="nb-btn px-2 py-0.5 text-[11px]"
        :disabled="!manageName.trim()"
        :title="t('firmware.configEditor.renameTitle')"
        @click="renameSelected"
      >
        {{ t('firmware.configEditor.rename') }}
      </button>
      <button
        class="nb-btn px-2 py-0.5 text-[11px]"
        :disabled="!manageName.trim()"
        :title="t('firmware.configEditor.duplicateTitle')"
        @click="duplicateSelected"
      >
        {{ t('firmware.configEditor.duplicate') }}
      </button>
    </div>

    <div
      v-if="selectedProfile"
      class="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-brutal border-2 border-ink bg-surface px-2 py-1 text-[11px]"
    >
      <span class="font-bold uppercase tracking-wide">{{ selectedProfile.name }}</span>
      <span :class="selectedProfile.built ? '' : 'opacity-50'">
        {{
          selectedProfile.built
            ? t('firmware.configEditor.builtVersion', {
                version: selectedProfile.built_version ?? '—',
              })
            : t('firmware.configEditor.notBuilt')
        }}
      </span>
      <span v-if="selectedProfile.is_linux" class="nb-badge bg-brand-yellow text-[10px]"
        >linux</span
      >
      <span v-if="selectedProfile.is_avr" class="nb-badge bg-brand-yellow text-[10px]">avr</span>
      <span v-if="selectedProfile.is_can_bridge" class="nb-badge bg-brand-yellow text-[10px]">{{
        t('firmware.configEditor.canBridge')
      }}</span>
    </div>

    <div v-if="error" class="nb-badge bg-brand-red text-surface">{{ error }}</div>
    <div v-else-if="loading" class="font-mono text-xs">
      {{ t('firmware.configEditor.loading') }}
    </div>

    <div v-else class="space-y-0.5">
      <template v-for="item in flat" :key="item.node.name">
        <div
          v-if="item.node.type === 'menu'"
          class="mt-1.5 text-[11px] font-bold uppercase opacity-70"
          :style="{ paddingLeft: item.depth * 12 + 'px' }"
        >
          {{ item.node.prompt }}
        </div>
        <div
          v-else-if="item.node.type === 'comment'"
          class="py-0.5 text-[11px] italic opacity-60"
          :style="{ paddingLeft: item.depth * 12 + 'px' }"
        >
          ❝ {{ item.node.prompt }}
        </div>
        <div v-else :style="{ paddingLeft: item.depth * 12 + 'px' }">
          <div
            class="flex items-center justify-between gap-2 rounded px-1 py-0.5"
            :class="
              isToggle(item.node)
                ? item.node.readonly
                  ? 'opacity-60'
                  : 'cursor-pointer select-none hover:bg-paper'
                : ''
            "
            @click="isToggle(item.node) && toggleBool(item.node)"
          >
            <span
              class="min-w-0 flex-1 truncate"
              :title="
                item.node.readonly
                  ? t('firmware.configEditor.lockedTitle')
                  : (item.node.help ?? item.node.name)
              "
            >
              {{ item.node.prompt }}
              <code
                v-if="showRaw && !item.node.name.startsWith('__')"
                class="ms-1 text-[10px] opacity-50"
                >{{ item.node.name }}</code
              >
            </span>
            <!-- bool/tristate: the whole row is the click target; this is the indicator -->
            <span
              v-if="isToggle(item.node)"
              class="nb-badge shrink-0"
              :class="boolOn(item.node) ? 'bg-brand-lime' : 'bg-surface opacity-70'"
            >
              {{ item.node.readonly ? '🔒 ' : ''
              }}{{
                boolOn(item.node) ? t('firmware.configEditor.on') : t('firmware.configEditor.off')
              }}
            </span>
            <select
              v-else-if="item.node.type === 'choice'"
              :class="inputClass"
              :value="item.node.value ?? ''"
              :disabled="item.node.readonly"
              @change="onSelect(item.node, $event)"
            >
              <option v-for="c in item.node.choices" :key="c.name" :value="c.name">
                {{ c.prompt }}
              </option>
            </select>
            <input
              v-else
              :class="[inputClass, 'font-mono']"
              :value="item.node.value ?? ''"
              :disabled="item.node.readonly"
              @change="onInput(item.node, $event)"
            />
          </div>
          <div
            v-if="(showRaw && item.node.dep_str) || (showHelp && item.node.default)"
            class="text-[10px] opacity-50"
          >
            <span v-if="showRaw && item.node.dep_str">{{
              t('firmware.configEditor.needs', { dep: item.node.dep_str })
            }}</span>
            <span v-if="showHelp && item.node.default" class="ms-2">{{
              t('firmware.configEditor.default', { value: item.node.default })
            }}</span>
          </div>
          <p v-if="showHelp && item.node.help" class="pb-1 text-[11px] leading-tight opacity-60">
            {{ item.node.help }}
          </p>
        </div>
      </template>
    </div>

    <div class="flex flex-wrap items-center gap-2 border-t-2 border-ink pt-2">
      <input
        v-model="profileName"
        :placeholder="t('firmware.configEditor.profileNamePlaceholder')"
        :class="['min-w-[8rem] flex-1', inputClass, 'max-w-none']"
      />
      <button
        class="nb-btn bg-brand-lime px-3 py-0.5 text-xs"
        :disabled="!profileName.trim() || saving"
        @click="save"
      >
        {{ saving ? t('firmware.configEditor.saving') : t('firmware.configEditor.saveProfile') }}
      </button>
    </div>
    <p v-if="message" class="font-mono text-[11px] opacity-70">{{ message }}</p>

    <pre
      v-if="buildLog"
      class="max-h-48 overflow-auto rounded-brutal border-2 border-ink bg-ink p-2 font-mono text-[11px] leading-tight text-surface"
      >{{ buildLog }}</pre
    >
  </div>
</template>
