/** Inbound cross-widget focus for the Machine Map (mirrors hardware-browser's useEntityFocus).
 *
 *  Another widget calls `focusTopologyNode('toolhead_mcu')` then `go('board-topology')`; the
 *  Machine Map watches the shared ref and selects that node once the topology is loaded. */
import { ref } from 'vue'

/** The MCU section name (e.g. `mcu`, `toolhead_mcu`) — or `host` — awaiting selection. */
export const pendingNode = ref<string | null>(null)

export function focusTopologyNode(section: string): void {
  pendingNode.value = section
}
