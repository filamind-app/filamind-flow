<script setup lang="ts">
/** Rules engine (suite-only / flow-A): safe-by-default IF-THEN automation. The engine has a master
 *  switch (off by default) and each rule is armed individually; gcode actions run only when the
 *  printer is idle (gated server-side). Shows the recent fire log. Builds rules visually.
 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import HelpDrawer from '@/components/ui/HelpDrawer.vue'
import { describeError } from '@/core/describeError'

import HelpIllo from './HelpIllo.vue'
import { GLOSSARY_KEYS, HELP_ILLO, HELP_TOPICS } from './help'
import { deleteRule, getRules, setEngine, upsertRule } from './api'
import { ACTIONS, HEATERS, TRIGGERS, emptyRule, type Rule, type RulesView } from './types'

const { t, locale } = useI18n({ useScope: 'global' })

const view = ref<RulesView>({ enabled: false, rules: [], log: [] })
const editing = ref<Rule | null>(null)
const error = ref<string | null>(null)
const busy = ref(false)
const confirmDelete = ref<string | null>(null)

const isTemp = computed(() => editing.value?.trigger.type.startsWith('temp_') ?? false)

function when(seconds: unknown): string {
  return typeof seconds === 'number'
    ? new Date(seconds * 1000).toLocaleTimeString(locale.value)
    : ''
}

async function refresh(): Promise<void> {
  error.value = null
  try {
    view.value = await getRules()
  } catch (e) {
    error.value = describeError(e)
  }
}

async function guard(fn: () => Promise<void>): Promise<void> {
  busy.value = true
  error.value = null
  try {
    await fn()
    await refresh()
  } catch (e) {
    error.value = describeError(e)
  } finally {
    busy.value = false
  }
}

const toggleEngine = () => guard(() => setEngine(!view.value.enabled))
const toggleArm = (r: Rule) =>
  guard(async () => {
    await upsertRule({ ...r, enabled: !r.enabled })
  })
function removeRule(id: string): void {
  confirmDelete.value = null
  void guard(() => deleteRule(id))
}

function startNew(): void {
  editing.value = emptyRule()
}
function startEdit(r: Rule): void {
  editing.value = JSON.parse(JSON.stringify(r))
}
function save(): void {
  const rule = editing.value
  if (!rule) return
  void guard(async () => {
    await upsertRule(rule)
    editing.value = null
  })
}

function triggerSummary(r: Rule): string {
  const base = t(`rules.triggers.${r.trigger.type}`)
  return isTempType(r.trigger.type) ? `${base}: ${r.trigger.heater} ${r.trigger.value}°C` : base
}
function actionSummary(r: Rule): string {
  return t(`rules.actions.${r.action.type}`)
}
function isTempType(type: string): boolean {
  return type === 'temp_above' || type === 'temp_below'
}

onMounted(refresh)
</script>

<template>
  <div class="space-y-3 text-sm">
    <div class="flex items-start justify-between gap-2">
      <p class="min-w-0 flex-1 text-xs opacity-70">{{ t('rules.intro') }}</p>
      <HelpDrawer
        class="shrink-0"
        namespace="rules"
        :topics="HELP_TOPICS"
        :illo-map="HELP_ILLO"
        :illo="HelpIllo"
        :glossary-keys="GLOSSARY_KEYS"
        :button-label="t('rules.help.guide')"
        :title="t('rules.help.guideTitle')"
        :close-label="t('rules.help.close')"
      />
    </div>

    <p v-if="error" class="nb-card bg-brand-red px-2 py-1 text-xs text-paper" role="alert">
      {{ error }}
    </p>

    <!-- Master switch -->
    <div class="nb-card flex items-center justify-between gap-2 bg-surface p-2">
      <div class="min-w-0">
        <p class="text-xs font-bold">
          {{ view.enabled ? t('rules.engine.on') : t('rules.engine.off') }}
        </p>
        <p class="text-[11px] opacity-60">{{ t('rules.engine.masterNote') }}</p>
      </div>
      <button
        class="nb-btn shrink-0 px-3 py-1"
        :class="view.enabled ? 'bg-brand-lime' : 'bg-surface'"
        :disabled="busy"
        @click="toggleEngine"
      >
        {{ view.enabled ? t('rules.engine.turnOff') : t('rules.engine.turnOn') }}
      </button>
    </div>

    <!-- Rules -->
    <p v-if="!view.rules.length" class="text-xs opacity-60">{{ t('rules.empty') }}</p>
    <ul class="space-y-2">
      <li v-for="r in view.rules" :key="r.id" class="nb-card space-y-1 bg-surface p-2">
        <div class="flex items-center justify-between gap-2">
          <span class="min-w-0 truncate font-bold">{{ r.name }}</span>
          <button
            class="nb-btn shrink-0 px-2 py-0.5 text-xs"
            :class="r.enabled ? 'bg-brand-lime' : 'bg-surface'"
            :disabled="busy"
            @click="toggleArm(r)"
          >
            {{ r.enabled ? t('rules.rule.armed') : t('rules.rule.arm') }}
          </button>
        </div>
        <p class="text-[11px] opacity-70">{{ triggerSummary(r) }} → {{ actionSummary(r) }}</p>
        <div class="flex flex-wrap gap-2">
          <button
            class="nb-btn bg-surface px-2 py-0.5 text-xs"
            :disabled="busy"
            @click="startEdit(r)"
          >
            {{ t('rules.rule.edit') }}
          </button>
          <template v-if="confirmDelete === r.id">
            <button
              class="nb-btn bg-brand-red px-2 py-0.5 text-xs text-paper"
              @click="removeRule(r.id)"
            >
              {{ t('rules.rule.confirmDelete') }}
            </button>
            <button class="nb-btn bg-surface px-2 py-0.5 text-xs" @click="confirmDelete = null">
              {{ t('rules.form.cancel') }}
            </button>
          </template>
          <button
            v-else
            class="nb-btn bg-surface px-2 py-0.5 text-xs"
            @click="confirmDelete = r.id"
          >
            {{ t('rules.rule.delete') }}
          </button>
        </div>
      </li>
    </ul>

    <button v-if="!editing" class="nb-btn bg-brand-cyan px-3 py-1" @click="startNew">
      {{ t('rules.form.add') }}
    </button>

    <!-- Editor -->
    <div v-if="editing" class="nb-card space-y-2 bg-surface p-2">
      <label class="flex flex-col gap-0.5 text-xs">
        {{ t('rules.form.name') }}
        <input
          v-model="editing.name"
          type="text"
          class="nb-input"
          :placeholder="t('rules.form.namePlaceholder')"
        />
      </label>

      <label class="flex flex-col gap-0.5 text-xs">
        {{ t('rules.form.trigger') }}
        <select v-model="editing.trigger.type" class="nb-input">
          <option v-for="x in TRIGGERS" :key="x" :value="x">{{ t(`rules.triggers.${x}`) }}</option>
        </select>
      </label>
      <div v-if="isTemp" class="grid grid-cols-2 gap-2">
        <label class="flex flex-col gap-0.5 text-xs">
          {{ t('rules.form.heater') }}
          <select v-model="editing.trigger.heater" class="nb-input">
            <option v-for="h in HEATERS" :key="h" :value="h">{{ h }}</option>
          </select>
        </label>
        <label class="flex flex-col gap-0.5 text-xs">
          {{ t('rules.form.value') }}
          <input v-model.number="editing.trigger.value" type="number" step="5" class="nb-input" />
        </label>
      </div>

      <label class="flex flex-col gap-0.5 text-xs">
        {{ t('rules.form.action') }}
        <select v-model="editing.action.type" class="nb-input">
          <option v-for="x in ACTIONS" :key="x" :value="x">{{ t(`rules.actions.${x}`) }}</option>
        </select>
      </label>
      <label v-if="editing.action.type === 'notify'" class="flex flex-col gap-0.5 text-xs">
        {{ t('rules.form.message') }}
        <input
          v-model="editing.action.message"
          type="text"
          class="nb-input"
          :placeholder="t('rules.form.messagePlaceholder')"
        />
      </label>
      <label v-else class="flex flex-col gap-0.5 text-xs">
        {{ t('rules.form.gcode') }}
        <input
          v-model="editing.action.gcode"
          type="text"
          class="nb-input font-mono"
          :placeholder="t('rules.form.gcodePlaceholder')"
        />
      </label>

      <div class="flex gap-2">
        <button class="nb-btn bg-brand-lime px-3 py-1" :disabled="busy" @click="save">
          {{ t('rules.form.save') }}
        </button>
        <button class="nb-btn bg-surface px-3 py-1" @click="editing = null">
          {{ t('rules.form.cancel') }}
        </button>
      </div>
    </div>

    <!-- Fire log -->
    <div v-if="view.log.length" class="nb-card space-y-1 bg-surface p-2">
      <p class="text-xs font-bold">{{ t('rules.log.title') }}</p>
      <ul class="space-y-0.5 font-mono text-[11px]">
        <li v-for="(e, i) in view.log" :key="i" class="flex flex-wrap gap-x-2 opacity-80">
          <span class="opacity-60">{{ when(e.time) }}</span>
          <span class="font-bold">{{ e.rule }}</span>
          <span>{{ t(`rules.log.outcome.${e.outcome}`) }}</span>
        </li>
      </ul>
    </div>
  </div>
</template>
