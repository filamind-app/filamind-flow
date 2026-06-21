<script setup lang="ts">
/** Material Brain - the first-class filament-profile manager (flow-A / suite-only). Browse, add,
 *  edit and delete saved materials; each shows a flow verdict cross-checking its max volumetric
 *  flow against the configured hotend's catalog ceiling (so an over-ambitious profile is flagged
 *  before it shows up as under-extrusion). SET_MATERIAL apply lands in a later step.
 */
import { onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import HelpDrawer from '@/components/ui/HelpDrawer.vue'
import { describeError } from '@/core/describeError'

import HelpIllo from './HelpIllo.vue'
import { GLOSSARY_KEYS, HELP_ILLO, HELP_TOPICS } from './help'
import { applyMaterial, deleteMaterial, flowCheck, listMaterials, saveMaterial } from './api'
import { emptyProfile, type MaterialFlowCheck, type MaterialProfile } from './types'

const { t } = useI18n({ useScope: 'global' })

const materials = ref<MaterialProfile[]>([])
const checks = reactive<Record<string, MaterialFlowCheck>>({})
const loading = ref(false)
const error = ref<string | null>(null)
const notice = ref<{ text: string; ok: boolean } | null>(null)
const form = ref<MaterialProfile | null>(null)
const editingId = ref<string | null>(null)
const saving = ref(false)

async function refreshChecks(): Promise<void> {
  await Promise.all(
    materials.value.map(async (m) => {
      try {
        checks[m.id] = await flowCheck(m.id)
      } catch {
        /* a missing verdict just hides the badge */
      }
    }),
  )
}

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    materials.value = await listMaterials()
    await refreshChecks()
  } catch (e) {
    error.value = describeError(e)
  } finally {
    loading.value = false
  }
}

function startAdd(): void {
  editingId.value = null
  form.value = emptyProfile()
}

function startEdit(m: MaterialProfile): void {
  editingId.value = m.id
  form.value = { ...m }
}

function cancel(): void {
  form.value = null
  editingId.value = null
}

async function submit(): Promise<void> {
  if (!form.value) return
  saving.value = true
  error.value = null
  try {
    await saveMaterial(form.value, editingId.value ?? undefined)
    cancel()
    await load()
  } catch (e) {
    error.value = describeError(e)
  } finally {
    saving.value = false
  }
}

async function remove(m: MaterialProfile): Promise<void> {
  error.value = null
  try {
    await deleteMaterial(m.id)
    await load()
  } catch (e) {
    error.value = describeError(e)
  }
}

function verdictText(check: MaterialFlowCheck): string {
  const tt = t as unknown as (key: string, named: Record<string, unknown>) => string
  return tt(`material.flowCheck.${check.code}`, check.params ?? {})
}

async function doApply(m: MaterialProfile): Promise<void> {
  notice.value = null
  error.value = null
  try {
    const res = await applyMaterial(m.id)
    const tt = t as unknown as (key: string, named: Record<string, unknown>) => string
    notice.value = { text: tt(`material.apply.${res.code}`, res.params ?? {}), ok: res.ok }
  } catch (e) {
    error.value = describeError(e)
  }
}

onMounted(load)
</script>

<template>
  <div class="space-y-3 text-sm">
    <div class="flex items-start justify-between gap-2">
      <p class="min-w-0 flex-1 text-xs opacity-70">{{ t('material.intro') }}</p>
      <HelpDrawer
        class="shrink-0"
        namespace="material"
        :topics="HELP_TOPICS"
        :illo-map="HELP_ILLO"
        :illo="HelpIllo"
        :glossary-keys="GLOSSARY_KEYS"
        :button-label="t('material.help.guide')"
        :title="t('material.help.guideTitle')"
        :close-label="t('material.help.close')"
      />
    </div>

    <div class="flex items-center gap-2">
      <button v-if="!form" class="nb-btn bg-brand-lime px-3 py-1" @click="startAdd">
        <span aria-hidden="true">＋</span> {{ t('material.add') }}
      </button>
      <span v-if="loading" class="text-xs opacity-60">{{ t('material.loading') }}</span>
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

    <!-- Add / edit form -->
    <form v-if="form" class="nb-card space-y-2 bg-surface p-2" @submit.prevent="submit">
      <div class="grid grid-cols-2 gap-2">
        <label class="col-span-2 flex flex-col gap-0.5 text-xs">
          {{ t('material.fields.name') }}
          <input v-model="form.name" required class="nb-input" />
        </label>
        <label class="flex flex-col gap-0.5 text-xs">
          {{ t('material.fields.material') }}
          <input v-model="form.material" class="nb-input" />
        </label>
        <label class="flex flex-col gap-0.5 text-xs">
          {{ t('material.fields.brand') }}
          <input v-model="form.brand" class="nb-input" />
        </label>
        <label class="flex flex-col gap-0.5 text-xs">
          {{ t('material.fields.color') }}
          <input v-model="form.color" class="nb-input" />
        </label>
        <label class="flex flex-col gap-0.5 text-xs">
          {{ t('material.fields.diameter') }}
          <input v-model.number="form.diameter" type="number" step="0.01" class="nb-input" />
        </label>
        <label class="flex flex-col gap-0.5 text-xs">
          {{ t('material.fields.density') }}
          <input v-model.number="form.density" type="number" step="0.01" class="nb-input" />
        </label>
        <label class="flex flex-col gap-0.5 text-xs">
          {{ t('material.fields.maxFlow') }}
          <input
            v-model.number="form.max_volumetric_flow"
            type="number"
            step="0.5"
            class="nb-input"
          />
        </label>
        <label class="flex flex-col gap-0.5 text-xs">
          {{ t('material.fields.nozzleTemp') }}
          <input v-model.number="form.nozzle_temp" type="number" class="nb-input" />
        </label>
        <label class="flex flex-col gap-0.5 text-xs">
          {{ t('material.fields.bedTemp') }}
          <input v-model.number="form.bed_temp" type="number" class="nb-input" />
        </label>
        <label class="col-span-2 flex flex-col gap-0.5 text-xs">
          {{ t('material.fields.notes') }}
          <input v-model="form.notes" class="nb-input" />
        </label>
      </div>
      <div class="flex gap-2">
        <button type="submit" class="nb-btn bg-brand-lime px-3 py-1" :disabled="saving">
          {{ t('material.save') }}
        </button>
        <button type="button" class="nb-btn bg-surface px-3 py-1" @click="cancel">
          {{ t('material.cancel') }}
        </button>
      </div>
    </form>

    <!-- Saved profiles -->
    <p v-if="!materials.length && !loading" class="text-xs opacity-60">{{ t('material.empty') }}</p>
    <ul v-else class="space-y-1.5">
      <li
        v-for="m in materials"
        :key="m.id"
        class="nb-card flex flex-wrap items-center gap-x-2 gap-y-1 bg-paper px-2 py-1.5"
      >
        <span class="font-bold">{{ m.name }}</span>
        <span class="font-mono text-[11px] opacity-70">{{ m.material }}</span>
        <span v-if="m.max_volumetric_flow > 0" class="font-mono text-[11px] opacity-70">
          {{ t('material.list.flow', { v: m.max_volumetric_flow }) }}
        </span>
        <span
          v-if="checks[m.id] && checks[m.id].code !== 'unset' && checks[m.id].code !== 'no_ceiling'"
          class="nb-badge text-[10px]"
          :class="checks[m.id].level === 'warn' ? 'bg-brand-red text-paper' : 'bg-brand-lime'"
        >
          {{ verdictText(checks[m.id]) }}
        </span>
        <span class="ms-auto flex gap-1">
          <button class="nb-btn bg-brand-cyan px-2 py-0.5 text-[11px]" @click="doApply(m)">
            {{ t('material.apply.button') }}
          </button>
          <button class="nb-btn bg-surface px-2 py-0.5 text-[11px]" @click="startEdit(m)">
            {{ t('material.edit') }}
          </button>
          <button class="nb-btn bg-surface px-2 py-0.5 text-[11px]" @click="remove(m)">
            {{ t('material.delete') }}
          </button>
        </span>
      </li>
    </ul>
  </div>
</template>
