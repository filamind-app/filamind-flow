import { defineAsyncComponent, defineComponent, h, type Component } from 'vue'

import { registerWidget } from '@/core/registry'
import type { WidgetDefinition } from '@/core/registry/types'
import { isWidgetEnabled, isWidgetGated } from '@/core/host/adapter'
import { suiteUnlocked } from '@/core/host/suite'

/**
 * Wrap a suite-gated widget so it renders its REAL UI once the suite is unlocked (FilaMind 3D
 * detected installed, or the suite build) and the install-required gate otherwise. The choice is
 * reactive (`suiteUnlocked`), so installing FilaMind 3D flips the widget on with no rebuild - the
 * widget's data is served by the flow backend, so it works the moment it's unlocked.
 */
function gatedComponent(id: string, real: Component): Component {
  const SuiteGate = defineAsyncComponent(() => import('@/components/SuiteGate.vue'))
  return defineComponent({
    name: `suite-gated-${id}`,
    setup: () => () => (suiteUnlocked.value ? h(real) : h(SuiteGate, { widgetId: id })),
  })
}

/** Register a widget for the current host; gated widgets register with the reactive gate wrapper. */
function reg(def: WidgetDefinition): void {
  if (!isWidgetEnabled(def.id)) return
  registerWidget(
    isWidgetGated(def.id) ? { ...def, component: gatedComponent(def.id, def.component) } : def,
  )
}

/**
 * Feature widget registration hub. Each feature registers a `WidgetDefinition`
 * here; keep components lazy (`defineAsyncComponent`) so each widget is its own
 * chunk, loaded only when shown.
 */
export function registerWidgets(): void {
  reg({
    id: 'machine-doctor',
    title: 'Machine Doctor',
    icon: '🩺',
    description: 'One-click full-printer scan with an A-F report card and jump-to-fix links.',
    component: defineAsyncComponent(() => import('./machine-doctor/MachineDoctorWidget.vue')),
  })

  reg({
    id: 'firmware-upgrade',
    title: 'Firmware Manager',
    icon: '🔧',
    description: 'MCU firmware versions, host sync status, and toolchain readiness.',
    defaultSize: { w: 2, h: 1 },
    component: defineAsyncComponent(() => import('./firmware-upgrade/FirmwareUpgradeWidget.vue')),
  })

  reg({
    id: 'input-shaping',
    title: 'Input Shaping',
    icon: '📈',
    description: 'Analyze a resonance CSV and find the best input shaper.',
    component: defineAsyncComponent(() => import('./input-shaping/InputShapingWidget.vue')),
  })

  reg({
    id: 'material-brain',
    title: 'Material Brain',
    icon: '🧠',
    description: 'Saved filament profiles with a flow-vs-hotend-ceiling check.',
    component: defineAsyncComponent(() => import('./material-brain/MaterialBrainWidget.vue')),
  })

  reg({
    id: 'tuning',
    title: 'Tuning Wizards',
    icon: '🎚',
    description: 'Guided calibration wizards (Pressure Advance first).',
    component: defineAsyncComponent(() => import('./tuning/TuningWidget.vue')),
  })

  reg({
    id: 'preflight',
    title: 'Pre-Print Check',
    icon: '🚦',
    description: 'A read-only readiness check before starting a print.',
    component: defineAsyncComponent(() => import('./preflight/PreflightWidget.vue')),
  })

  reg({
    id: 'known-good-pack',
    title: 'Known-Good Packs',
    icon: '🗄',
    description: 'Snapshot your working config and restore it after a bad edit.',
    component: defineAsyncComponent(() => import('./known-good-pack/KnownGoodPackWidget.vue')),
  })

  reg({
    id: 'rules',
    title: 'Rules Engine',
    icon: '⚡',
    description: 'Safe IF-THEN automation: when something happens, run an action.',
    component: defineAsyncComponent(() => import('./rules/RulesWidget.vue')),
  })

  reg({
    id: 'motor-drivers',
    title: 'Motor Drivers',
    icon: '⚙',
    description: 'Live TMC stepper-driver inventory: current, mode, microsteps, and status.',
    defaultSize: { w: 2, h: 1 },
    component: defineAsyncComponent(() => import('./motor-drivers/MotorDriversWidget.vue')),
  })

  reg({
    id: 'config-editor',
    title: 'Config Editor',
    icon: '📝',
    description: "Browse your printer's config files, parsed into sections with validation.",
    defaultSize: { w: 2, h: 1 },
    component: defineAsyncComponent(() => import('./config-editor/ConfigEditorWidget.vue')),
  })

  reg({
    id: 'max-flow',
    title: 'Max-Flow',
    icon: '🌡',
    description: 'Measure the highest volumetric flow your hotend can sustain (StallGuard).',
    defaultSize: { w: 2, h: 1 },
    component: defineAsyncComponent(() => import('./max-flow/MaxFlowWidget.vue')),
  })

  reg({
    id: 'board-topology',
    title: 'Board Topology',
    icon: '🔌',
    description: 'See how the host and MCUs connect (USB / CAN / UART) + a board guess.',
    defaultSize: { w: 2, h: 1 },
    component: defineAsyncComponent(() => import('./board-topology/BoardTopologyWidget.vue')),
  })

  reg({
    id: 'macro-designer',
    title: 'Macro Designer',
    icon: '🧩',
    description: 'Simulate G-code offline - toolhead path, bounds, totals, and a macro library.',
    defaultSize: { w: 2, h: 1 },
    component: defineAsyncComponent(() => import('./macro-designer/MacroDesignerWidget.vue')),
  })

  reg({
    id: 'hardware-browser',
    title: 'Hardware Browser',
    icon: '🔎',
    description: 'Search a curated 3D-printing hardware reference by name, manufacturer, or spec.',
    defaultSize: { w: 2, h: 1 },
    component: defineAsyncComponent(() => import('./hardware-browser/HardwareBrowserWidget.vue')),
  })

  reg({
    id: 'screen-manager',
    title: 'Screen Manager',
    icon: '🖥',
    description:
      "Manage your printer's touchscreen UI: settings, menus, themes, and which screen runs.",
    defaultSize: { w: 2, h: 1 },
    component: defineAsyncComponent(() => import('./screen-manager/ScreenManagerWidget.vue')),
  })

  reg({
    id: 'config-templates',
    title: 'Config Templates',
    icon: '📋',
    description: 'Ready-to-paste Klipper config blocks and macros, by category.',
    defaultSize: { w: 2, h: 1 },
    component: defineAsyncComponent(() => import('./config-templates/ConfigTemplatesWidget.vue')),
  })

  reg({
    id: 'host-control',
    title: 'Host Control',
    icon: '🖧',
    description:
      "Manage the printer host's Linux OS: health, services, disk cleanup, and system settings.",
    defaultSize: { w: 2, h: 1 },
    component: defineAsyncComponent(() => import('./host-control/HostControlWidget.vue')),
  })

  // Ships in BOTH hosts (the one infrastructure exception) - it's how components get installed.
  reg({
    id: 'setup',
    title: 'Setup',
    icon: '📦',
    description: 'Browse and manage Klipper-ecosystem components for this printer.',
    defaultSize: { w: 2, h: 1 },
    component: defineAsyncComponent(() => import('./setup/SetupWidget.vue')),
  })
}
