/** Inbound cross-widget focus for Motor Drivers: jump to (and briefly highlight) one stepper's
 *  card — e.g. from a Machine Map component chip or a doctor finding. */
import { ref } from 'vue'

export const pendingStepper = ref<string | null>(null)

export function focusStepper(stepper: string): void {
  pendingStepper.value = stepper
}
