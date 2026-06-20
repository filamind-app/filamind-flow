import { defineAsyncComponent } from 'vue'

import { registerWidget } from '@/core/registry'
import type { WidgetDefinition } from '@/core/registry/types'
import { isWidgetEnabled } from '@/core/host/adapter'

/** Register a widget only if the current host enables it (dual-host gate). */
function reg(def: WidgetDefinition): void {
  if (isWidgetEnabled(def.id)) registerWidget(def)
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
    id: 'klipperscreen-studio',
    title: 'KlipperScreen Studio',
    icon: '🖥',
    description: "Edit your printer's KlipperScreen touchscreen config and restart it to apply.",
    defaultSize: { w: 2, h: 1 },
    component: defineAsyncComponent(
      () => import('./klipperscreen-studio/KlipperScreenStudioWidget.vue'),
    ),
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

  // Ships in BOTH hosts (the one infrastructure exception) — it's how components get installed.
  reg({
    id: 'setup',
    title: 'Setup',
    icon: '📦',
    description: 'Browse and manage Klipper-ecosystem components for this printer.',
    defaultSize: { w: 2, h: 1 },
    component: defineAsyncComponent(() => import('./setup/SetupWidget.vue')),
  })

  // Suite-only (gated in adapter.ts): steer the on-printer FilaMind screen from here.
  reg({
    id: 'remote-control',
    title: 'Remote Control',
    icon: '📡',
    description:
      'Steer the on-printer FilaMind screen — switch its tab, show a message, or locate it.',
    defaultSize: { w: 2, h: 1 },
    component: defineAsyncComponent(() => import('./remote-control/RemoteControlWidget.vue')),
  })
}
