import type { WidgetDefinition } from './types'

/**
 * In-memory registry of dashboard widgets.
 *
 * This is the extensibility core: the scaffold ships empty, and features add
 * themselves via `registerWidget` at startup (see src/widgets/index.ts).
 */
class WidgetRegistry {
  private readonly widgets = new Map<string, WidgetDefinition>()

  /** Registers a widget. Throws on a duplicate id to catch copy-paste mistakes early. */
  register(widget: WidgetDefinition): void {
    if (this.widgets.has(widget.id)) {
      throw new Error(`Widget "${widget.id}" is already registered`)
    }
    this.widgets.set(widget.id, widget)
  }

  /** Returns a widget by id, or undefined. */
  get(id: string): WidgetDefinition | undefined {
    return this.widgets.get(id)
  }

  /** Returns every registered widget, in registration order. */
  all(): WidgetDefinition[] {
    return [...this.widgets.values()]
  }

  /**
   * Aggregates the subscription requirements of every registered widget into a
   * single object map. `null` (all fields) wins over a specific field list.
   */
  aggregateSubscriptions(): Record<string, string[] | null> {
    const merged: Record<string, string[] | null> = {}
    for (const widget of this.widgets.values()) {
      if (!widget.subscriptions) continue
      for (const [object, fields] of Object.entries(widget.subscriptions)) {
        if (merged[object] === null || fields === null) {
          merged[object] = null
        } else {
          merged[object] = [...new Set([...(merged[object] ?? []), ...fields])]
        }
      }
    }
    return merged
  }

  /** Removes all widgets. Intended for tests and HMR. */
  clear(): void {
    this.widgets.clear()
  }
}

/** The shared registry singleton. */
export const widgetRegistry = new WidgetRegistry()

/** Convenience wrapper used by feature modules. */
export function registerWidget(widget: WidgetDefinition): void {
  widgetRegistry.register(widget)
}
