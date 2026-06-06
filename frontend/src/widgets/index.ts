import { defineAsyncComponent } from 'vue'

import { registerWidget } from '@/core/registry'

/**
 * Feature widget registration hub. Each feature registers a `WidgetDefinition`
 * here; keep components lazy (`defineAsyncComponent`) so each widget is its own
 * chunk, loaded only when shown.
 */
export function registerWidgets(): void {
  registerWidget({
    id: 'firmware-upgrade',
    title: 'Firmware Manager',
    icon: '🔧',
    description: 'MCU firmware versions, host sync status, and toolchain readiness.',
    defaultSize: { w: 2, h: 1 },
    component: defineAsyncComponent(() => import('./firmware-upgrade/FirmwareUpgradeWidget.vue')),
  })

  registerWidget({
    id: 'input-shaping',
    title: 'Input Shaping',
    icon: '📈',
    description: 'Analyze a resonance CSV and find the best input shaper.',
    component: defineAsyncComponent(() => import('./input-shaping/InputShapingWidget.vue')),
  })

  registerWidget({
    id: 'motor-drivers',
    title: 'Motor Drivers',
    icon: '⚙',
    description: 'Live TMC stepper-driver inventory: current, mode, microsteps, and status.',
    defaultSize: { w: 2, h: 1 },
    component: defineAsyncComponent(() => import('./motor-drivers/MotorDriversWidget.vue')),
  })

  registerWidget({
    id: 'config-editor',
    title: 'Config Editor',
    icon: '📝',
    description: "Browse your printer's config files, parsed into sections with validation.",
    defaultSize: { w: 2, h: 1 },
    component: defineAsyncComponent(() => import('./config-editor/ConfigEditorWidget.vue')),
  })

  registerWidget({
    id: 'max-flow',
    title: 'Max-Flow',
    icon: '🌡',
    description: 'Measure the highest volumetric flow your hotend can sustain (StallGuard).',
    defaultSize: { w: 2, h: 1 },
    component: defineAsyncComponent(() => import('./max-flow/MaxFlowWidget.vue')),
  })

  registerWidget({
    id: 'board-topology',
    title: 'Board Topology',
    icon: '🔌',
    description: 'See how the host and MCUs connect (USB / CAN / UART) + a board guess.',
    defaultSize: { w: 2, h: 1 },
    component: defineAsyncComponent(() => import('./board-topology/BoardTopologyWidget.vue')),
  })

  registerWidget({
    id: 'macro-designer',
    title: 'Macro Designer',
    icon: '🧩',
    description: 'Simulate G-code offline — toolhead path, bounds, totals, and a macro library.',
    defaultSize: { w: 2, h: 1 },
    component: defineAsyncComponent(() => import('./macro-designer/MacroDesignerWidget.vue')),
  })

  registerWidget({
    id: 'hardware-browser',
    title: 'Hardware Browser',
    icon: '🔎',
    description: 'Search a curated 3D-printing hardware reference by name, manufacturer, or spec.',
    defaultSize: { w: 2, h: 1 },
    component: defineAsyncComponent(() => import('./hardware-browser/HardwareBrowserWidget.vue')),
  })
}
