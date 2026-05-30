import type { Component } from 'vue'

/** Preferred grid footprint for a widget, in dashboard columns. */
export interface WidgetSize {
  /** Column span (1–4). */
  w: number
  /** Row span hint (reserved for future grid layouts). */
  h: number
}

/**
 * A self-contained dashboard feature.
 *
 * Widgets register themselves at startup and are rendered by the dashboard.
 * Keep `component` lazy (defineAsyncComponent) so a widget's code is only
 * downloaded when it is actually shown.
 */
export interface WidgetDefinition {
  /** Stable, unique id, e.g. "temperature". Used for layout persistence. */
  id: string
  /** Human-readable title shown in the widget header. */
  title: string
  /** Short description for a future widget catalog. */
  description?: string
  /** Optional grouping category. */
  category?: string
  /** The Vue component to render. Prefer an async component for code-splitting. */
  component: Component
  /** Default grid footprint. */
  defaultSize?: WidgetSize
  /**
   * Printer objects this widget needs subscribed, e.g. `{ extruder: null }`.
   * The dashboard aggregates these across all widgets and subscribes once.
   */
  subscriptions?: Record<string, string[] | null>
}
