// The SENDER side of the cross-surface command bus, flow-native. Moonraker only lets connections
// that identified as type:"agent" call connection.send_event, so this owns a SECOND, lightweight
// MoonrakerClient (separate from flow's main data connection) dedicated to the command bus. It
// carries no subscriptions - it identifies as an agent and emits UI-only commands; the on-printer
// FilaMind screen receives them via notify_agent_event and acts.

import { MoonrakerClient } from '../moonraker/client'
import { resolveEndpoints } from '../moonraker/config'
import {
  FILAMIND_COMMAND_EVENT,
  type RemoteCommand,
  type RemoteView,
  type RemoteMessageLevel,
} from './commands'

export interface CommandSenderOptions {
  /** Stable agent name (pinned - a drifting name registers phantom duplicates on reconnect). */
  client_name: string
  version: string
  /** Moonraker documents `url` as mandatory for identify. */
  url: string
  /** Fires whenever readiness flips (connected + identified) - lets a UI gate its send affordances. */
  onReadyChange?: (ready: boolean) => void
}

export class CommandSender {
  private readonly client: MoonrakerClient
  private identified = false
  private identifying?: Promise<void>
  private ready_ = false
  private retryTimer?: ReturnType<typeof setTimeout>
  private retryDelayMs = 500

  constructor(private readonly opts: CommandSenderOptions) {
    this.client = new MoonrakerClient({ url: resolveEndpoints().wsUrl })
    this.client.onStateChange((s) => {
      if (s === 'connected') {
        // Moonraker forgets the agent identity on every (re)open → re-identify each time.
        this.identified = false
        void this.ensureIdentified().catch(() => this.scheduleRetry())
      } else {
        // connecting / reconnecting / closed / error / idle → not ready
        this.clearRetry()
        this.setIdentified(false)
      }
    })
  }

  /** true only when the bus is connected AND identified - gate remote-control affordances on this. */
  get ready(): boolean {
    return this.ready_
  }

  /** Open the agent connection (lazy - call when the remote-control surface is first used). The
   *  store keeps it warm for the app's lifetime; the browser reaps the socket on page unload. */
  start(): void {
    this.client.connect()
  }

  /** Broadcast a UI-only command. Best-effort: dropped (not queued/replayed) when the bus is down -
   *  a stale "navigate" replayed later would yank a screen unexpectedly. */
  async send(cmd: RemoteCommand): Promise<void> {
    if (this.client.state !== 'connected') return
    try {
      await this.ensureIdentified()
      await this.client.call('connection.send_event', { event: FILAMIND_COMMAND_EVENT, data: cmd })
    } catch {
      /* best-effort UI nudge */
    }
  }

  navigate(view: RemoteView): Promise<void> {
    return this.send({ kind: 'navigate', view })
  }
  message(level: RemoteMessageLevel, text: string): Promise<void> {
    return this.send({ kind: 'message', level, text: text.slice(0, 280) })
  }
  locate(): Promise<void> {
    return this.send({ kind: 'locate' })
  }

  private ensureIdentified(): Promise<void> {
    if (this.identified) return Promise.resolve()
    if (this.identifying) return this.identifying
    this.identifying = this.client
      .call('server.connection.identify', {
        client_name: this.opts.client_name,
        version: this.opts.version,
        type: 'agent',
        url: this.opts.url,
      })
      .then(() => this.setIdentified(true))
      .finally(() => {
        this.identifying = undefined
      })
    return this.identifying
  }

  private setIdentified(v: boolean): void {
    this.identified = v
    if (v) {
      this.retryDelayMs = 500
      this.clearRetry()
    }
    this.refreshReady()
  }

  private refreshReady(): void {
    const r = this.client.state === 'connected' && this.identified
    if (r !== this.ready_) {
      this.ready_ = r
      this.opts.onReadyChange?.(r)
    }
  }

  /** Self-heal a transient identify failure while the socket stays connected (Moonraker busy during
   *  a klippy/print transition can time out identify without dropping the connection). Bounded backoff. */
  private scheduleRetry(): void {
    if (this.retryTimer || this.identified) return
    if (this.client.state !== 'connected') return
    const delay = this.retryDelayMs
    this.retryDelayMs = Math.min(this.retryDelayMs * 2, 10_000)
    this.retryTimer = setTimeout(() => {
      this.retryTimer = undefined
      if (this.client.state === 'connected' && !this.identified) {
        void this.ensureIdentified().catch(() => this.scheduleRetry())
      }
    }, delay)
  }

  private clearRetry(): void {
    if (this.retryTimer) {
      clearTimeout(this.retryTimer)
      this.retryTimer = undefined
    }
  }
}
