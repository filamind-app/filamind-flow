<script setup lang="ts">
/** Guided new-board walkthrough (#118). A checklist that reflects the LIVE firmware state and
 *  deep-links into the existing tabs — it deliberately does NOT duplicate the build/flash logic
 *  (firmware flashing is hands-on: bootloader, confirms, …). Each step turns green once the live
 *  state satisfies it, and its button opens the tab where you do that step.
 */
import { computed } from 'vue'

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
    label: 'Detect your board',
    why: 'Connect the board (USB / CAN / DFU) and scan so FilaMind can see it.',
    done: props.boardsScanned > 0,
    action: { label: 'Scan in Devices →', tab: 'devices' },
  },
  {
    id: 'configure',
    label: 'Configure & build a profile',
    why: "Pick the board's Klipper options (Kconfig) and build the firmware once as a reusable profile.",
    done: props.builtProfiles > 0,
    action: { label: 'Configure →', tab: 'configure' },
  },
  {
    id: 'assign',
    label: 'Add & assign the device',
    why: "Register the board and give it the profile + how it's flashed.",
    done: props.operational > 0,
    action: { label: 'Devices →', tab: 'devices' },
  },
  {
    id: 'flash',
    label: 'Build & flash, then verify',
    why: "Flash the firmware (behind a confirm), then check the board's reported version matches the host.",
    done: props.operational > 0 && props.outdated === 0,
    action: { label: 'Status →', tab: 'status' },
  },
])

const allDone = computed(() => steps.value.every((s) => s.done))
// The first unfinished step is the one to do now.
const currentId = computed(() => steps.value.find((s) => !s.done)?.id ?? null)
</script>

<template>
  <div class="space-y-2 rounded-brutal border-2 border-ink bg-paper p-2 text-sm">
    <div class="text-xs font-bold uppercase tracking-wide">🧭 Guided — flash a new board</div>
    <p
      v-if="allDone"
      class="rounded-brutal border-2 border-ink bg-brand-lime px-2 py-1 text-[11px]"
    >
      ✓ All set — every registered board is built and in sync with the host.
    </p>
    <p v-else class="text-[11px] opacity-70">
      Four steps to get a new control board running matching firmware. Each opens the right tab and
      turns green once it's done.
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
        <p class="pl-7 text-[10px] leading-snug opacity-70">{{ s.why }}</p>
      </li>
    </ol>
  </div>
</template>
