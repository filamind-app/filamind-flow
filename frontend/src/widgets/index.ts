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
    title: 'Firmware Upgrade',
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
}
