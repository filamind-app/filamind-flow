<script setup lang="ts">
/** Tuning wizards (suite-only / flow-A). A picker over guided TUNING_TOWER wizards - each plans a
 *  tower, you read the cleanest Z height off the print, and the wizard computes + applies the
 *  matching value (gated). Pressure Advance and retraction ship today; more slot in via TowerWizard.
 */
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

import HelpDrawer from '@/components/ui/HelpDrawer.vue'

import HelpIllo from './HelpIllo.vue'
import TowerWizard from './TowerWizard.vue'
import TempWizard from './TempWizard.vue'
import FlowWizard from './FlowWizard.vue'
import { GLOSSARY_KEYS, HELP_ILLO, HELP_TOPICS } from './help'
import { applyPa, applyRetraction, planPa, planRetraction } from './api'
import { defaultParams, defaultRetractionParams } from './types'

const { t } = useI18n({ useScope: 'global' })

type WizardId = 'pa' | 'retraction' | 'temp' | 'flow'
const active = ref<WizardId>('pa')

const TABS: { id: WizardId; titleKey: string }[] = [
  { id: 'pa', titleKey: 'tuning.pa.title' },
  { id: 'retraction', titleKey: 'tuning.retraction.title' },
  { id: 'temp', titleKey: 'tuning.temp.title' },
  { id: 'flow', titleKey: 'tuning.flow.title' },
]
</script>

<template>
  <div class="space-y-3 text-sm">
    <div class="flex items-start justify-between gap-2">
      <p class="min-w-0 flex-1 text-xs opacity-70">{{ t('tuning.intro') }}</p>
      <HelpDrawer
        class="shrink-0"
        namespace="tuning"
        :topics="HELP_TOPICS"
        :illo-map="HELP_ILLO"
        :illo="HelpIllo"
        :glossary-keys="GLOSSARY_KEYS"
        :button-label="t('tuning.help.guide')"
        :title="t('tuning.help.guideTitle')"
        :close-label="t('tuning.help.close')"
      />
    </div>

    <!-- Wizard picker -->
    <div class="flex flex-wrap gap-2" role="tablist" :aria-label="t('tuning.pick.label')">
      <button
        v-for="tab in TABS"
        :key="tab.id"
        type="button"
        role="tab"
        :aria-selected="active === tab.id"
        class="nb-btn px-3 py-1 text-xs"
        :class="active === tab.id ? 'bg-brand-purple text-paper' : 'bg-surface'"
        @click="active = tab.id"
      >
        {{ t(tab.titleKey) }}
      </button>
    </div>

    <!-- Wizards kept mounted (v-show) so switching tabs preserves each one's progress. -->
    <TowerWizard
      v-show="active === 'pa'"
      base="tuning.pa"
      params-base="tuning.params"
      value-key="pa"
      :defaults="defaultParams()"
      :plan="planPa"
      :apply="applyPa"
    />
    <TowerWizard
      v-show="active === 'retraction'"
      base="tuning.retraction"
      params-base="tuning.retraction.params"
      value-key="value"
      :defaults="defaultRetractionParams()"
      :plan="planRetraction"
      :apply="applyRetraction"
    />
    <TempWizard v-show="active === 'temp'" />
    <FlowWizard v-show="active === 'flow'" />
  </div>
</template>
