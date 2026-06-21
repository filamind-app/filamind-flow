<script setup lang="ts">
/** Shown in place of a widget that needs the FilaMind 3D host when running in the Mainsail build.
 *  It states the requirement and what the tool does; the real widget renders in the suite build.
 *  Bound to a widget id by the registry (see widgets/index.ts) so it can show that widget's name.
 */
import { useI18n } from 'vue-i18n'

const props = defineProps<{ widgetId: string }>()

const { t } = useI18n({ useScope: 'global' })
const tt = t as unknown as (key: string, named?: Record<string, unknown>) => string
</script>

<template>
  <div class="text-sm">
    <div class="nb-card flex items-start gap-3 bg-surface p-3">
      <span class="shrink-0 text-2xl" aria-hidden="true">🧩</span>
      <div class="min-w-0 space-y-1">
        <p class="font-display text-base font-bold">{{ t('shell.gate.title') }}</p>
        <p class="text-xs opacity-80">
          {{ tt('shell.gate.body', { name: t(`shell.widgets.${props.widgetId}.title`) }) }}
        </p>
        <p class="text-[11px] opacity-60">
          {{ t(`shell.widgets.${props.widgetId}.description`) }}
        </p>
      </div>
    </div>
  </div>
</template>
