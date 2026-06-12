/** "On this printer" awareness for the Hardware Browser: catalog ids of the hardware actually
 *  detected on the connected machine (boards/MCUs/host from the live topology, TMC models from
 *  the live config, motors from the assignment mapping). Fetched once per mount; panels read the
 *  shared sets to badge matching entities, and the widget renders a My-Hardware strip. */
import { reactive } from 'vue'

import { resolveEndpoints } from '@/core/moonraker'

export interface OnPrinter {
  reachable: boolean
  loaded: boolean
  boards: Set<string>
  mcus: Set<string>
  drivers: Set<string>
  motors: Set<string>
  hosts: Set<string>
}

export const onPrinter = reactive<OnPrinter>({
  reachable: true,
  loaded: false,
  boards: new Set(),
  mcus: new Set(),
  drivers: new Set(),
  motors: new Set(),
  hosts: new Set(),
})

export async function loadOnPrinter(): Promise<void> {
  try {
    const { backendUrl } = resolveEndpoints()
    const response = await fetch(`${backendUrl}/api/hardware/on-printer`)
    if (!response.ok) throw new Error(String(response.status))
    const body = (await response.json()) as {
      reachable: boolean
      boards: string[]
      mcus: string[]
      drivers: string[]
      motors: string[]
      hosts: string[]
    }
    onPrinter.reachable = body.reachable
    onPrinter.boards = new Set(body.boards)
    onPrinter.mcus = new Set(body.mcus)
    onPrinter.drivers = new Set(body.drivers)
    onPrinter.motors = new Set(body.motors)
    onPrinter.hosts = new Set(body.hosts)
    onPrinter.loaded = true
  } catch {
    onPrinter.reachable = false
    onPrinter.loaded = true
  }
}
