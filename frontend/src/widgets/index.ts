/**
 * Feature widget registration hub.
 *
 * The scaffold intentionally ships with NO widgets. To add a feature:
 *   1. create `src/widgets/<feature>/<Feature>Widget.vue`;
 *   2. build a `WidgetDefinition` (see core/registry/types.ts), using
 *      `defineAsyncComponent(() => import('./<feature>/<Feature>Widget.vue'))`
 *      so each widget is a separate, lazily-loaded chunk;
 *   3. register it below with `registerWidget(...)`.
 */
export function registerWidgets(): void {
  // Intentionally empty — feature widgets are registered here.
}
