<script setup lang="ts">
/** Host Control · Boot · Splash studio — design a boot-splash PNG on a canvas (background colour,
 *  a text line, an optional uploaded image) and apply it. The apply is a gated backend write to a
 *  known splash path; whether it shows at boot depends on the host's splash setup (see the caveat). */
import { onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { describeError } from '@/core/describeError'

import { setBootSplash } from './api'

const { t } = useI18n({ useScope: 'global' })
const emit = defineEmits<{ applied: [] }>()

const W = 480
const H = 320
const canvas = ref<HTMLCanvasElement | null>(null)
const bg = ref('#0f1419')
const text = ref('FilaMind')
const fg = ref('#e6edf3')
const busy = ref(false)
const note = ref<string | null>(null)
const error = ref<string | null>(null)
let uploaded: HTMLImageElement | null = null

function draw(): void {
  const c = canvas.value
  const ctx = c?.getContext('2d')
  if (!c || !ctx) return
  ctx.fillStyle = bg.value
  ctx.fillRect(0, 0, W, H)
  if (uploaded) {
    const r = Math.min((W * 0.7) / uploaded.width, (H * 0.55) / uploaded.height)
    const w = uploaded.width * r
    const h = uploaded.height * r
    ctx.drawImage(uploaded, (W - w) / 2, H * 0.18, w, h)
  }
  if (text.value) {
    ctx.fillStyle = fg.value
    ctx.font = 'bold 44px system-ui, sans-serif'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText(text.value, W / 2, uploaded ? H * 0.82 : H / 2)
  }
}

onMounted(draw)
watch([bg, text, fg], draw)

function onUpload(e: Event): void {
  const f = (e.target as HTMLInputElement).files?.[0]
  if (!f) return
  const img = new Image()
  img.onload = () => {
    uploaded = img
    draw()
  }
  img.src = URL.createObjectURL(f)
}

async function apply(): Promise<void> {
  const c = canvas.value
  if (!c) return
  busy.value = true
  note.value = null
  error.value = null
  try {
    const res = await setBootSplash(c.toDataURL('image/png'))
    if (res.ok) {
      note.value = t('hostControl.boot.studio.applied')
      emit('applied')
    } else {
      error.value = res.needs_setup
        ? t('hostControl.system.needsSetup')
        : res.output || t('hostControl.boot.studio.failed')
    }
  } catch (e) {
    error.value = describeError(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="nb-card space-y-3 bg-surface p-3">
    <p class="text-xs font-bold">{{ t('hostControl.boot.studio.title') }}</p>

    <div class="flex flex-wrap items-start gap-3">
      <canvas
        ref="canvas"
        :width="W"
        :height="H"
        class="h-auto w-full max-w-72 rounded-brutal border-2 border-ink"
        :aria-label="t('hostControl.boot.studio.title')"
      ></canvas>

      <div class="min-w-44 flex-1 space-y-2 text-xs">
        <label class="flex items-center gap-2">
          <span class="w-20 shrink-0 opacity-60">{{ t('hostControl.boot.studio.bg') }}</span>
          <input v-model="bg" type="color" class="h-7 w-10 rounded-sm border-2 border-ink" />
        </label>
        <label class="flex items-center gap-2">
          <span class="w-20 shrink-0 opacity-60">{{ t('hostControl.boot.studio.text') }}</span>
          <input
            v-model="text"
            type="text"
            maxlength="24"
            class="min-w-0 flex-1 rounded-sm border-2 border-ink bg-paper px-2 py-1"
          />
        </label>
        <label class="flex items-center gap-2">
          <span class="w-20 shrink-0 opacity-60">{{ t('hostControl.boot.studio.textColor') }}</span>
          <input v-model="fg" type="color" class="h-7 w-10 rounded-sm border-2 border-ink" />
        </label>
        <label class="flex items-center gap-2">
          <span class="w-20 shrink-0 opacity-60">{{ t('hostControl.boot.studio.upload') }}</span>
          <input
            type="file"
            accept="image/*"
            class="min-w-0 flex-1 text-[11px]"
            @change="onUpload"
          />
        </label>
      </div>
    </div>

    <div class="flex flex-wrap items-center gap-2">
      <button class="nb-btn bg-brand-lime px-3 py-1 text-xs" :disabled="busy" @click="apply">
        {{ busy ? t('hostControl.boot.studio.applying') : t('hostControl.boot.studio.apply') }}
      </button>
      <span class="text-[11px] opacity-60">{{ t('hostControl.boot.studio.caveat') }}</span>
    </div>

    <p v-if="note" class="text-[11px] font-bold text-brand-lime">✓ {{ note }}</p>
    <p v-if="error" role="alert" class="nb-card bg-brand-red/10 p-2 font-mono text-[11px]">
      {{ error }}
    </p>
  </div>
</template>
