/** Inbound cross-widget focus for the Config Editor.
 *
 *  A diagnostic anywhere in the app (the Machine Map's pin atlas, a doctor finding…) can call
 *  `focusConfigSection('stepper_x')` (optionally with the file) then `go('config-editor')`; the
 *  editor opens the file, expands that section in the structured view, and scrolls to it. With
 *  no file given it looks in the current file first, then locates the section via the
 *  project-wide search. */
import { ref } from 'vue'

export interface ConfigFocusTarget {
  /** Section header to open (matched case-insensitively; a bare type matches `type name` too). */
  section: string
  /** Config path, when the caller knows it; otherwise the editor resolves it. */
  file?: string
}

export const pendingSection = ref<ConfigFocusTarget | null>(null)

export function focusConfigSection(section: string, file?: string): void {
  // Reassign a fresh object so repeated jumps to the same section still trigger watchers.
  pendingSection.value = { section, file }
}
