/** Mirrors the rules-engine backend. */
export interface RuleTrigger {
  type: string
  heater?: string | null
  value?: number | null
}

export interface RuleAction {
  type: string
  message?: string | null
  gcode?: string | null
}

export interface Rule {
  id: string
  name: string
  enabled: boolean
  trigger: RuleTrigger
  action: RuleAction
}

export interface RulesView {
  enabled: boolean
  rules: Rule[]
  log: Array<Record<string, unknown>>
}

export const TRIGGERS = ['print_complete', 'print_error', 'temp_above', 'temp_below'] as const
export const ACTIONS = ['notify', 'gcode'] as const
export const HEATERS = ['extruder', 'extruder1', 'extruder2', 'heater_bed'] as const

export function emptyRule(): Rule {
  return {
    id: '',
    name: '',
    enabled: false,
    trigger: { type: 'print_complete', heater: 'extruder', value: 200 },
    action: { type: 'notify', message: '', gcode: '' },
  }
}
