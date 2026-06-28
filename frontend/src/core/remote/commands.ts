// Cross-surface remote-control command protocol (sender side). FilaMind flow broadcasts UI-only
// commands over Moonraker's agent-event bus so the on-printer FilaMind screen can be steered from
// here. Commands navigate/annotate the screen - they never touch the printer (not §12 writes).
//
// This mirrors the suite's @filamind/core protocol; flow keeps its own copy because it does not
// depend on that package. flow only SENDS, so the receiver-side validators live on the screen.

/** The single agent-event name FilaMind uses on the bus. */
export const FILAMIND_COMMAND_EVENT = 'filamind:command'

/** Views a screen-style surface can be told to show (matches the touch app's tabs). */
export type RemoteView = 'status' | 'control' | 'settings'
export const REMOTE_VIEWS: readonly RemoteView[] = ['status', 'control', 'settings']

export type RemoteMessageLevel = 'info' | 'warn'
export const REMOTE_MESSAGE_LEVELS: readonly RemoteMessageLevel[] = ['info', 'warn']

/** A UI-only instruction sent from one surface to another. */
export type RemoteCommand =
  | { kind: 'navigate'; view: RemoteView }
  | { kind: 'message'; level: RemoteMessageLevel; text: string }
  | { kind: 'locate' }
