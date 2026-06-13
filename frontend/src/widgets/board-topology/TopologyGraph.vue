<script setup lang="ts">
/** The "Machine Map" — a dependency-free SVG node-graph of the printer's control boards.
 *
 *  Two layouts of the SAME live data, cross-faded by the `view` prop:
 *   - LOGICAL: how Klipper sees it — the host at the apex, every MCU a child reached over its serial
 *     link (USB / CAN / UART), edges colour-coded by bus.
 *   - PHYSICAL: how it's actually built — an integrated SBC is drawn INSIDE the mainboard it ships
 *     on (e.g. an SV08 / Manta carrying a CB1), CAN MCUs hang off a shared backbone rail, and
 *     USB / UART boards are separate point-to-point units.
 *
 *  Pure presentation over `GET /api/topology`; emits `select` so the parent can drive an inspector.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { McuFirmware } from '@/widgets/firmware-upgrade/types'

import type { Topology, TopologyMcu } from './types'

const props = withDefaults(
  defineProps<{
    topology: Topology
    view: 'logical' | 'physical'
    selected: string | null
    /** Live per-MCU firmware/link telemetry, keyed by MCU name (empty when Moonraker is down). */
    health?: Record<string, McuFirmware | undefined>
  }>(),
  { health: () => ({}) },
)
const emit = defineEmits<{ select: [id: string] }>()

const { t } = useI18n({ useScope: 'global' })

const NW = 170
const NH = 58
const CW = 222
const CH = 130
const PAD = 10

interface NodeBox {
  id: string
  kind: 'host' | 'mcu'
  x: number
  y: number
  w: number
  h: number
  title: string
  /** Full, untruncated name for the node's <title> tooltip (the visible label is truncated). */
  full?: string
  sub?: string
  conn?: TopologyMcu['connection']
  match?: TopologyMcu['board_match']
  board?: string | null
  chassis?: boolean
  nested?: boolean
  integratedBadge?: boolean
}
interface EdgeLine {
  id: string
  d: string
  bus: string
  backbone?: boolean
  /** The MCU this edge leads to — so an out-of-sync MCU can flash its link. */
  target?: string
}
interface Layout {
  nodes: NodeBox[]
  edges: EdgeLine[]
  w: number
  h: number
}

function trunc(s: string, n = 20): string {
  s = (s || '').trim()
  return s.length > n ? s.slice(0, n - 1) + '…' : s
}

/** A vertical (parent-below) connector. */
function vEdge(x1: number, y1: number, x2: number, y2: number): string {
  const my = (y1 + y2) / 2
  return `M${x1},${y1} C${x1},${my} ${x2},${my} ${x2},${y2}`
}
/** A horizontal (anchor-to-side) connector. */
function hEdge(x1: number, y1: number, x2: number, y2: number): string {
  const mx = (x1 + x2) / 2
  return `M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`
}

const mcus = computed(() => props.topology.mcus ?? [])
const host = computed(() => props.topology.host)

function hostBox(x: number, y: number, w: number, h: number, nested = false): NodeBox {
  const hh = host.value
  return {
    id: 'host',
    kind: 'host',
    x,
    y,
    w,
    h,
    title: trunc(
      hh?.name && hh.name !== 'host' ? hh.name : t('boardTopology.host.label'),
      nested ? 22 : 24,
    ),
    full: hh?.name && hh.name !== 'host' ? hh.name : t('boardTopology.host.label'),
    sub: t('boardTopology.host.role'),
    nested,
  }
}

function mcuBox(m: TopologyMcu, x: number, y: number, w = NW, h = NH, chassis = false): NodeBox {
  return {
    id: 'mcu:' + m.name,
    kind: 'mcu',
    x,
    y,
    w,
    h,
    title: trunc(m.name, 18),
    full: m.name,
    sub: m.mcu || m.mcu_family || undefined,
    conn: m.connection,
    match: m.board_match,
    board: m.board_id,
    chassis,
  }
}

function logical(): Layout {
  const list = mcus.value
  const gap = 26
  const topY = PAD
  const rowY = topY + NH + 74
  const rowW = Math.max(list.length * NW + (list.length - 1) * gap, NW)
  const w = Math.max(rowW + PAD * 2, NW + 80, 360)
  const hostX = (w - NW) / 2
  const startX = (w - rowW) / 2
  const nodes: NodeBox[] = [hostBox(hostX, topY, NW, NH)]
  const edges: EdgeLine[] = []
  list.forEach((m, i) => {
    const x = startX + i * (NW + gap)
    nodes.push(mcuBox(m, x, rowY))
    edges.push({
      id: 'e' + i,
      d: vEdge(hostX + NW / 2, topY + NH, x + NW / 2, rowY),
      bus: m.connection,
      target: m.name,
    })
  })
  return { nodes, edges, w, h: rowY + NH + PAD }
}

function physical(): Layout {
  const list = mcus.value
  const integratedId = host.value?.integrated_into_board_id || null
  const primary =
    (integratedId && list.find((m) => m.board_id === integratedId)) ||
    list.find((m) => m.name === 'mcu') ||
    list[0]
  const others = list.filter((m) => m !== primary)
  const can = others.filter((m) => m.connection === 'canbus')
  const p2p = others.filter((m) => m.connection !== 'canbus')
  const nodes: NodeBox[] = []
  const edges: EdgeLine[] = []
  const integrated = !!(integratedId && primary && primary.board_id === integratedId)

  // Anchor = the chassis (integrated) or the primary mainboard node; the host is nested or separate.
  let aRight: number, aBottomX: number, aBottom: number, aRightY: number
  if (integrated && primary) {
    const cx = PAD
    const cy = PAD
    const chassis = mcuBox(primary, cx, cy, CW, CH, true)
    chassis.integratedBadge = true
    nodes.push(chassis)
    nodes.push(hostBox(cx + 14, cy + CH - 50, CW - 28, 38, true))
    aRight = cx + CW
    aRightY = cy + CH / 2
    aBottomX = cx + CW / 2
    aBottom = cy + CH
  } else if (primary) {
    nodes.push(hostBox(PAD, PAD, NW, NH))
    const py = PAD + NH + 44
    nodes.push(mcuBox(primary, PAD, py))
    edges.push({
      id: 'eh',
      d: vEdge(PAD + NW / 2, PAD + NH, PAD + NW / 2, py),
      bus: primary.connection,
      target: primary.name,
    })
    aRight = PAD + NW
    aRightY = py + NH / 2
    aBottomX = PAD + NW / 2
    aBottom = py + NH
  } else {
    nodes.push(hostBox(PAD, PAD, NW, NH))
    aRight = PAD + NW
    aRightY = PAD + NH / 2
    aBottomX = PAD + NW / 2
    aBottom = PAD + NH
  }

  // USB / UART boards: separate point-to-point units stacked to the right of the anchor.
  const rightX = aRight + 64
  p2p.forEach((m, i) => {
    const y = PAD + i * (NH + 20)
    nodes.push(mcuBox(m, rightX, y))
    edges.push({
      id: 'p' + i,
      d: hEdge(aRight, aRightY, rightX, y + NH / 2),
      bus: m.connection,
      target: m.name,
    })
  })

  // CAN boards: a shared backbone rail below the anchor, toolheads hanging off it.
  let canBottom = 0
  if (can.length) {
    const bbY = aBottom + 46
    const x1 = PAD + 18
    const x2 = Math.max(x1 + 120, PAD + 18 + can.length * (NW + 22))
    edges.push({ id: 'bb-drop', d: vEdge(aBottomX, aBottom, aBottomX, bbY), bus: 'canbus' })
    edges.push({ id: 'bb', d: `M${x1},${bbY} L${x2},${bbY}`, bus: 'canbus', backbone: true })
    can.forEach((m, i) => {
      const x = PAD + 18 + i * (NW + 22)
      const y = bbY + 34
      nodes.push(mcuBox(m, x, y))
      edges.push({
        id: 'c' + i,
        d: vEdge(x + NW / 2, bbY, x + NW / 2, y),
        bus: 'canbus',
        target: m.name,
      })
    })
    canBottom = bbY + 34 + NH
  }

  const w =
    Math.max(
      rightX + (p2p.length ? NW : 0),
      PAD + CW,
      can.length ? PAD + 18 + can.length * (NW + 22) : 0,
      360,
    ) + PAD
  const h = Math.max(aBottom, PAD + p2p.length * (NH + 20), canBottom, CH + PAD) + PAD
  return { nodes, edges, w, h }
}

const layout = computed<Layout>(() => (props.view === 'physical' ? physical() : logical()))

function busClass(bus: string): string {
  return (
    {
      canbus: 'bus-canbus',
      usb: 'bus-usb',
      uart: 'bus-uart',
    }[bus] || 'bus-unknown'
  )
}

function connLabel(conn?: string): string {
  return conn
    ? t('boardTopology.conn.' + (conn in { canbus: 1, usb: 1, uart: 1 } ? conn : 'unknown'))
    : ''
}

function ariaFor(n: NodeBox): string {
  if (n.kind === 'host') return t('boardTopology.host.label') + ': ' + n.title
  return n.title + (n.sub ? ', ' + n.sub : '') + (n.conn ? ', ' + connLabel(n.conn) : '')
}

// ── live link health (from /api/firmware/status, joined by MCU name) ────────────────────────────
type Health = 'ok' | 'warn' | 'out' | 'unknown'
function mcuNameOf(id: string): string {
  return id.startsWith('mcu:') ? id.slice(4) : ''
}
function healthOf(id: string): Health {
  const f = props.health[mcuNameOf(id)]
  if (!f || f.in_sync == null) return 'unknown'
  if (f.in_sync === false) return 'out' // firmware out of sync with the host — needs a restart/flash
  if ((f.retransmits ?? 0) > 1000 || (f.awake ?? 0) > 0.6) return 'warn' // flaky link / high load
  return 'ok'
}
const HEALTH_GLYPH: Record<Health, string> = { ok: '✓', warn: '⚠', out: '✕', unknown: '' }
function targetHealth(target?: string): Health {
  return target ? healthOf('mcu:' + target) : 'unknown'
}
function vitals(id: string): string {
  const f = props.health[mcuNameOf(id)]
  if (!f) return ''
  const parts: string[] = []
  if (f.freq != null)
    parts.push(t('boardTopology.graph.vitals.freq', { mhz: (f.freq / 1e6).toFixed(2) }))
  if (f.retransmits != null) parts.push(t('boardTopology.graph.vitals.retx', { n: f.retransmits }))
  if (f.awake != null)
    parts.push(t('boardTopology.graph.vitals.load', { pct: Math.round(f.awake * 100) }))
  const sync =
    f.in_sync === false
      ? t('boardTopology.sync.outOfSync')
      : f.in_sync
        ? t('boardTopology.sync.synced')
        : ''
  return [sync, ...parts].filter(Boolean).join(' · ')
}
</script>

<template>
  <div class="nb-card min-w-0 overflow-hidden bg-paper p-1">
    <!-- Scroll wrapper: on a wide column the SVG fills it (scales up, readable); on a narrow
         phone min-width holds it at full intrinsic size and this pans, instead of shrinking the
         graph to an illegible thumbnail. -->
    <div class="overflow-x-auto" style="-webkit-overflow-scrolling: touch">
      <svg
        :viewBox="`0 0 ${layout.w} ${layout.h}`"
        class="block h-auto select-none md:max-h-[460px]"
        :style="{ width: '100%', minWidth: layout.w + 'px', direction: 'ltr' }"
        role="img"
        :aria-label="t('boardTopology.graph.aria', { n: mcus.length })"
      >
        <Transition name="vfade">
          <g :key="view">
            <!-- Edges first (under nodes) -->
            <path
              v-for="e in layout.edges"
              :key="e.id"
              :d="e.d"
              class="edge"
              :class="[
                busClass(e.bus),
                { backbone: e.backbone, 'edge-alert': targetHealth(e.target) === 'out' },
              ]"
              fill="none"
            />
            <!-- Nodes -->
            <g
              v-for="n in layout.nodes"
              :key="n.id"
              :transform="`translate(${n.x},${n.y})`"
              class="node"
              :class="{
                'is-selected': selected === n.id,
                nested: n.nested,
                'is-alert': healthOf(n.id) === 'out',
              }"
              role="button"
              tabindex="0"
              :aria-label="ariaFor(n)"
              @click="emit('select', n.id)"
              @keydown.enter.prevent="emit('select', n.id)"
              @keydown.space.prevent="emit('select', n.id)"
            >
              <title>
                {{
                  n.kind === 'mcu' && healthOf(n.id) !== 'unknown'
                    ? n.full + ' — ' + vitals(n.id)
                    : n.full
                }}
              </title>
              <rect
                :width="n.w"
                :height="n.h"
                rx="5"
                class="node-rect stroke-ink"
                :class="
                  n.kind === 'host'
                    ? n.nested
                      ? 'fill-sbc'
                      : 'fill-host'
                    : n.chassis
                      ? 'fill-board'
                      : 'fill-mcu'
                "
              />
              <!-- live link-health: left-edge bar + status glyph (colour + glyph, never colour-only) -->
              <template v-if="n.kind === 'mcu' && healthOf(n.id) !== 'unknown'">
                <rect
                  x="2.5"
                  y="3"
                  width="3.5"
                  :height="n.h - 6"
                  rx="1.5"
                  :class="'health-bar h-' + healthOf(n.id)"
                />
                <text
                  :x="n.w - 8"
                  :y="n.chassis ? n.h - 8 : 15"
                  text-anchor="end"
                  :class="'t-health h-' + healthOf(n.id)"
                >
                  {{ HEALTH_GLYPH[healthOf(n.id)] }}
                </text>
              </template>
              <!-- chassis label (mainboard) -->
              <text v-if="n.chassis" x="10" y="18" class="t-title text-ink">{{ n.title }}</text>
              <text
                v-else-if="n.kind === 'host'"
                :x="10"
                :y="n.nested ? 16 : 20"
                class="t-title text-ink"
              >
                <tspan v-if="n.nested" class="t-soc">🖥</tspan>
                {{ n.title }}
              </text>
              <text v-else x="10" y="20" class="t-title text-ink">{{ n.title }}</text>

              <!-- sub line (chip / role) -->
              <text
                v-if="n.sub"
                x="10"
                :y="n.kind === 'host' && n.nested ? 30 : 36"
                class="t-sub text-ink"
              >
                {{ n.sub }}
              </text>

              <!-- integrated badge on the chassis -->
              <g v-if="n.integratedBadge" :transform="`translate(${n.w - 92},8)`">
                <rect width="84" height="16" rx="3" class="fill-sbc stroke-ink badge-rect" />
                <text x="42" y="12" text-anchor="middle" class="t-badge text-ink">
                  {{ t('boardTopology.graph.integrated') }}
                </text>
              </g>

              <!-- connection badge + board match on a regular MCU node -->
              <g
                v-if="n.kind === 'mcu' && !n.chassis && n.conn"
                :transform="`translate(10,${n.h - 18})`"
              >
                <rect
                  width="46"
                  height="13"
                  rx="3"
                  class="stroke-ink badge-rect"
                  :class="busClass(n.conn)"
                />
                <text x="23" y="10" text-anchor="middle" class="t-badge text-ink">
                  {{ connLabel(n.conn) }}
                </text>
              </g>
              <g
                v-if="n.kind === 'mcu' && n.board && !n.chassis"
                :transform="`translate(${n.w - 22},${n.h - 18})`"
              >
                <text
                  class="t-badge"
                  :class="n.match === 'confirmed' ? 'ok-text' : 'sug-text'"
                  text-anchor="end"
                >
                  {{ n.match === 'confirmed' ? '✓' : '◉' }}
                </text>
              </g>
            </g>
          </g>
        </Transition>
      </svg>
    </div>
  </div>
</template>

<style scoped>
.edge {
  stroke-width: 2.5;
  opacity: 0.85;
}
.edge.backbone {
  stroke-width: 5;
  opacity: 0.9;
}
.edge.edge-alert {
  stroke: rgb(var(--c-brand-red));
  stroke-width: 3.5;
  animation: edgepulse 1.1s ease-in-out infinite;
}
@keyframes edgepulse {
  50% {
    opacity: 0.35;
  }
}
.bus-canbus {
  stroke: rgb(var(--c-brand-cyan));
}
.bus-usb {
  stroke: rgb(var(--c-brand-lime));
}
.bus-uart {
  stroke: rgb(var(--c-brand-yellow));
}
.bus-unknown {
  stroke: rgb(var(--c-ink) / 0.4);
}
.node {
  cursor: pointer;
}
.node:focus {
  outline: none;
}
.node-rect {
  stroke-width: 2.5;
  transition: filter 0.15s;
}
.node.nested .node-rect {
  stroke-width: 2;
}
.node:hover .node-rect,
.node:focus .node-rect {
  filter: drop-shadow(2px 2px 0 rgb(var(--c-ink)));
}
.node.is-selected .node-rect {
  stroke: rgb(var(--c-brand-pink));
  stroke-width: 3.5;
  filter: drop-shadow(3px 3px 0 rgb(var(--c-ink)));
}
/* Live link-health — left-edge bar + status glyph (green ✓ / amber ⚠ / red ✕). */
.health-bar {
  stroke: rgb(var(--c-ink) / 0.5);
  stroke-width: 0.5;
}
.t-health {
  font:
    700 12px/1 ui-monospace,
    monospace;
}
.h-ok {
  fill: rgb(var(--c-brand-lime));
}
.h-warn {
  fill: rgb(var(--c-brand-yellow));
}
.h-out {
  fill: rgb(var(--c-brand-red));
}
/* An out-of-sync MCU gently pulses to draw the eye to the problem. */
.node.is-alert .node-rect {
  animation: nodepulse 1.4s ease-in-out infinite;
}
@keyframes nodepulse {
  50% {
    filter: drop-shadow(0 0 5px rgb(var(--c-brand-red)));
  }
}
@media (prefers-reduced-motion: reduce) {
  .edge.edge-alert,
  .node.is-alert .node-rect {
    animation: none;
  }
}
.fill-host {
  fill: rgb(var(--c-brand-yellow));
}
.fill-sbc {
  fill: rgb(var(--c-brand-blue) / 0.55);
}
.fill-board {
  fill: rgb(var(--c-brand-cyan) / 0.25);
}
.fill-mcu {
  fill: rgb(var(--c-surface));
}
.badge-rect {
  stroke-width: 1.5;
}
.bus-canbus.badge-rect {
  fill: rgb(var(--c-brand-cyan));
}
.bus-usb.badge-rect {
  fill: rgb(var(--c-brand-lime));
}
.bus-uart.badge-rect {
  fill: rgb(var(--c-brand-yellow));
}
.bus-unknown.badge-rect {
  fill: rgb(var(--c-paper));
}
.stroke-ink {
  stroke: rgb(var(--c-ink));
}
.text-ink {
  fill: rgb(var(--c-ink));
}
.ok-text {
  fill: rgb(var(--c-brand-lime));
  stroke: rgb(var(--c-ink));
  stroke-width: 0.5;
}
.sug-text {
  fill: rgb(var(--c-ink) / 0.55);
}
.t-title {
  font:
    700 13px/1 ui-monospace,
    monospace;
}
.t-sub {
  font:
    400 10px/1 ui-monospace,
    monospace;
  opacity: 0.7;
}
.t-badge {
  font:
    700 9px/1 ui-monospace,
    monospace;
}
.vfade-enter-active,
.vfade-leave-active {
  transition: opacity 0.35s ease;
}
.vfade-enter-from,
.vfade-leave-to {
  opacity: 0;
}
</style>
