<script setup lang="ts">
/** Guided new-board walkthrough (#118). A checklist that reflects the LIVE firmware state and
 *  deep-links into the existing tabs — it deliberately does NOT duplicate the build/flash logic
 *  (firmware flashing is hands-on: bootloader, confirms, …). Each step turns green once the live
 *  state satisfies it, and its button opens the tab where you do that step.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n({ useScope: 'global' })

type Tab = 'status' | 'configure' | 'devices' | 'external'

const props = defineProps<{
  boardsScanned: number
  builtProfiles: number
  operational: number
  outdated: number
}>()
const emit = defineEmits<{ go: [tab: Tab] }>()

interface Step {
  id: string
  label: string
  why: string
  done: boolean
  action: { label: string; tab: Tab }
}

const steps = computed<Step[]>(() => [
  {
    id: 'detect',
    label: t('firmware.guided.stepDetectLabel'),
    why: t('firmware.guided.stepDetectWhy'),
    done: props.boardsScanned > 0,
    action: { label: t('firmware.guided.stepDetectAction'), tab: 'devices' },
  },
  {
    id: 'configure',
    label: t('firmware.guided.stepConfigureLabel'),
    why: t('firmware.guided.stepConfigureWhy'),
    done: props.builtProfiles > 0,
    action: { label: t('firmware.guided.stepConfigureAction'), tab: 'configure' },
  },
  {
    id: 'assign',
    label: t('firmware.guided.stepAssignLabel'),
    why: t('firmware.guided.stepAssignWhy'),
    done: props.operational > 0,
    action: { label: t('firmware.guided.stepAssignAction'), tab: 'devices' },
  },
  {
    id: 'flash',
    label: t('firmware.guided.stepFlashLabel'),
    why: t('firmware.guided.stepFlashWhy'),
    done: props.operational > 0 && props.outdated === 0,
    action: { label: t('firmware.guided.stepFlashAction'), tab: 'status' },
  },
])

const allDone = computed(() => steps.value.every((s) => s.done))
// The first unfinished step is the one to do now.
const currentId = computed(() => steps.value.find((s) => !s.done)?.id ?? null)
</script>

<template>
  <div class="space-y-2 rounded-brutal border-2 border-ink bg-paper p-2 text-sm">
    <div class="text-xs font-bold uppercase tracking-wide">{{ t('firmware.guided.title') }}</div>
    <p
      v-if="allDone"
      class="rounded-brutal border-2 border-ink bg-brand-lime px-2 py-1 text-[11px]"
    >
      {{ t('firmware.guided.allDone') }}
    </p>
    <p v-else class="text-[11px] opacity-70">
      {{ t('firmware.guided.intro') }}
    </p>

    <ol class="space-y-1.5">
      <li
        v-for="(s, i) in steps"
        :key="s.id"
        class="rounded-brutal border-2 border-ink p-2"
        :class="s.id === currentId ? 'bg-surface ring-2 ring-ink' : s.done ? 'opacity-70' : ''"
      >
        <div class="flex items-center gap-2">
          <span
            class="flex h-5 w-5 shrink-0 items-center justify-center rounded-brutal border-2 border-ink text-[10px] font-bold"
            :class="s.done ? 'bg-brand-lime' : 'bg-surface'"
            >{{ s.done ? '✓' : i + 1 }}</span
          >
          <span class="min-w-0 flex-1 font-bold">{{ s.label }}</span>
          <button
            v-if="!s.done"
            class="nb-btn shrink-0 bg-brand-cyan px-2 py-0.5 text-[10px]"
            @click="emit('go', s.action.tab)"
          >
            {{ s.action.label }}
          </button>
        </div>
        <p class="ps-7 text-[10px] leading-snug opacity-70">{{ s.why }}</p>
      </li>
    </ol>
  </div>
</template>
