<script setup lang="ts">
/** The motor catalog view: browse the canonical motors[] entity — specs + a recommended
 *  Klipper run_current + community presets + a copyable config snippet. Mirrors BoardsPanel. */
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { describeError } from '@/core/describeError'

import { fetchMotorDetail, fetchMotors } from './api'
import RelatedChips from './RelatedChips.vue'
import type { MotorDetail, MotorSummary } from './types'
import { useEntityFocus } from './useEntityFocus'

const { t } = useI18n({ useScope: 'global' })
const LIMIT = 24

const q = ref('')
const motors = ref<MotorSummary[]>([])
const total = ref(0)
const offset = ref(0)
const loading = ref(true)
const error = ref<string | null>(null)

const openId = ref<string | null>(null)
const detailCache = ref<Record<string, MotorDetail>>({})
const detailLoading = ref<string | null>(null)

const hasNext = computed(() => offset.value + motors.value.length < total.value)
const hasPrev = computed(() => offset.value > 0)

async function load(reset = true): Promise<void> {
  if (reset) offset.value = 0
  loading.value = true
  try {
    const r = await fetchMotors({ q: q.value, limit: LIMIT, offset: offset.value })
    motors.value = r.motors
    total.value = r.total
    error.value = null
  } catch (e) {
    error.value = describeError(e)
  } finally {
    loading.value = false
  }
}

function page(delta: number): void {
  offset.value = Math.max(0, offset.value + delta * LIMIT)
  void load(false)
}

async function toggle(id: string): Promise<void> {
  if (openId.value === id) {
    openId.value = null
    return
  }
  openId.value = id
  if (!detailCache.value[id]) {
    detailLoading.value = id
    try {
      detailCache.value[id] = await fetchMotorDetail(id)
    } catch {
      openId.value = null
    } finally {
      detailLoading.value = null
    }
  }
}

const copied = ref<string | null>(null)
function copyConfig(id: string, text: string): void {
  void navigator.clipboard?.writeText(text)
  copied.value = id
  window.setTimeout(() => {
    if (copied.value === id) copied.value = null
  }, 1500)
}

const { focus } = useEntityFocus()
async function focusById(id: string, name?: string): Promise<void> {
  q.value = name ?? ''
  await load(true)
  if (openId.value !== id && motors.value.some((m) => m.motor_id === id)) void toggle(id)
}
watch(
  focus,
  (f) => {
    if (f && f.tab === 'motors') void focusById(f.id, f.name)
  },
  { immediate: true },
)

onMounted(() => void load(true))
</script>

<template>
  <div class="space-y-2 text-sm">
    <div class="flex flex-wrap items-end gap-2">
      <label class="min-w-[12rem] flex-1">
        <span class="mb-0.5 block text-[11px] opacity-70">{{
          t('hardwareBrowser.motors.search')
        }}</span>
        <input
          v-model="q"
          type="search"
          :placeholder="t('hardwareBrowser.motors.search')"
          class="w-full rounded-brutal border-2 border-ink bg-paper px-1.5 py-1 font-mono text-[11px]"
          @keyup.enter="load(true)"
        />
      </label>
      <button
        class="nb-btn bg-brand-cyan px-3 py-1 text-xs"
        :disabled="loading"
        @click="load(true)"
      >
        {{ t('hardwareBrowser.search.button') }}
      </button>
    </div>

    <p v-if="loading && !motors.length" class="font-mono text-xs opacity-70">
      {{ t('hardwareBrowser.states.loading') }}
    </p>
    <div v-else-if="error" class="nb-card space-y-2 bg-brand-red/10 p-2">
      <p class="font-mono text-[11px]">{{ error }}</p>
      <button class="nb-btn bg-surface px-2 py-1 text-xs" @click="load(false)">
        {{ t('hardwareBrowser.states.retry') }}
      </button>
    </div>

    <template v-else>
      <p class="font-mono text-[11px] opacity-60">
        {{ t('hardwareBrowser.motors.total', { n: total }) }}
      </p>
      <p v-if="!motors.length" class="font-mono text-xs opacity-70">
        {{ t('hardwareBrowser.motors.none') }}
      </p>

      <ul v-else class="space-y-2">
        <li v-for="m in motors" :key="m.motor_id" class="nb-card bg-surface p-2">
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0">
              <div class="truncate font-bold">{{ m.name }}</div>
              <div class="font-mono text-[10px] opacity-60">
                <span v-if="m.manufacturer">{{ m.manufacturer }} · </span>NEMA {{ m.nema }} ·
                {{ m.stepAngle }}
              </div>
            </div>
            <button
              class="nb-btn shrink-0 bg-brand-cyan px-2 py-0.5 text-[10px]"
              @click="toggle(m.motor_id)"
            >
              {{
                openId === m.motor_id
                  ? t('hardwareBrowser.boards.hide')
                  : t('hardwareBrowser.boards.view')
              }}
            </button>
          </div>

          <!-- headline chips -->
          <div class="mt-1 flex flex-wrap gap-1">
            <span v-if="m.ratedCurrent" class="rounded bg-paper px-1 font-mono text-[9px]">
              {{ t('hardwareBrowser.motors.rated') }} {{ m.ratedCurrent }}
            </span>
            <span
              v-if="m.recommendedRunCurrent"
              class="rounded bg-brand-lime px-1 font-mono text-[9px]"
            >
              {{ t('hardwareBrowser.motors.run') }} {{ m.recommendedRunCurrent }} A
            </span>
            <span v-if="m.holdingTorque" class="rounded bg-paper px-1 font-mono text-[9px]">
              {{ m.holdingTorque }}
            </span>
          </div>

          <!-- expanded detail -->
          <div v-if="openId === m.motor_id" class="mt-2 space-y-2 border-t-2 border-ink pt-2">
            <p v-if="detailLoading === m.motor_id" class="font-mono text-[11px] opacity-70">
              {{ t('boardTopology.board.loading') }}
            </p>
            <template v-else-if="detailCache[m.motor_id]">
              <!-- specs -->
              <dl
                v-if="Object.keys(detailCache[m.motor_id].specs || {}).length"
                class="grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5 font-mono text-[10px]"
              >
                <template v-for="(val, key) in detailCache[m.motor_id].specs" :key="key">
                  <dt class="opacity-60">{{ key }}</dt>
                  <dd class="min-w-0">{{ val }}</dd>
                </template>
              </dl>

              <!-- copy-ready Klipper config snippet -->
              <div v-if="detailCache[m.motor_id].configSnippet">
                <div class="flex items-center justify-between">
                  <span class="text-[10px] font-bold opacity-70">{{
                    t('hardwareBrowser.motors.config')
                  }}</span>
                  <button
                    class="nb-btn bg-brand-lime px-2 py-0 text-[9px]"
                    @click="copyConfig(m.motor_id, detailCache[m.motor_id].configSnippet || '')"
                  >
                    {{
                      copied === m.motor_id
                        ? t('hardwareBrowser.boards.copied')
                        : t('hardwareBrowser.boards.copy')
                    }}
                  </button>
                </div>
                <pre
                  class="overflow-x-auto rounded-brutal border-2 border-ink bg-paper p-2 text-[9px] leading-tight"
                  >{{ detailCache[m.motor_id].configSnippet }}</pre
                >
              </div>

              <!-- cross-entity links (its manufacturer) -->
              <RelatedChips :id="m.motor_id" type="motors" />
            </template>
          </div>
        </li>
      </ul>

      <div v-if="total > LIMIT" class="flex items-center justify-center gap-2">
        <button
          class="nb-btn bg-surface px-3 py-1 text-xs"
          :disabled="!hasPrev || loading"
          @click="page(-1)"
        >
          ‹ {{ t('hardwareBrowser.results.prev') }}
        </button>
        <button
          class="nb-btn bg-surface px-3 py-1 text-xs"
          :disabled="!hasNext || loading"
          @click="page(1)"
        >
          {{ t('hardwareBrowser.results.next') }} ›
        </button>
      </div>
    </template>
  </div>
</template>
