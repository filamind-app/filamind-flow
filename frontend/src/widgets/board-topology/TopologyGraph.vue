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

import type { Topology, TopologyMcu } from './types'

const props = defineProps<{
  topology: Topology
  view: 'logical' | 'physical'
  selected: string | null
}>()
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
    edges.push({ id: 'p' + i, d: hEdge(aRight, aRightY, rightX, y + NH / 2), bus: m.connection })
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
      edges.push({ id: 'c' + i, d: vEdge(x + NW / 2, bbY, x + NW / 2, y), bus: 'canbus' })
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
</script>

<template>
  <div class="nb-card overflow-hidden bg-paper p-1">
    <svg
      :viewBox="`0 0 ${layout.w} ${layout.h}`"
      class="h-auto w-full select-none"
      :style="{ maxHeight: '460px' }"
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
            :class="[busClass(e.bus), { backbone: e.backbone }]"
            fill="none"
          />
          <!-- Nodes -->
          <g
            v-for="n in layout.nodes"
            :key="n.id"
            :transform="`translate(${n.x},${n.y})`"
            class="node"
            :class="{ 'is-selected': selected === n.id, nested: n.nested }"
            role="button"
            tabindex="0"
            :aria-label="ariaFor(n)"
            @click="emit('select', n.id)"
            @keydown.enter.prevent="emit('select', n.id)"
            @keydown.space.prevent="emit('select', n.id)"
          >
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
              v-if="n.kind === 'mcu' && n.board"
              :transform="`translate(${n.w - (n.chassis ? 26 : 22)},${n.chassis ? 10 : n.h - 18})`"
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
