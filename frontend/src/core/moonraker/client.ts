import { resolveEndpoints } from './config'
import type {
  ConnectionState,
  JsonRpcError,
  JsonRpcMessage,
  JsonRpcNotification,
  JsonRpcSuccess,
} from './types'

interface PendingCall {
  resolve: (value: unknown) => void
  reject: (reason: Error) => void
  timer: ReturnType<typeof setTimeout>
}

type StateListener = (state: ConnectionState) => void
type NotificationListener = (params: unknown) => void

export interface MoonrakerClientOptions {
  /** WebSocket URL. Defaults to the resolved endpoint (host:7125/websocket). */
  url?: string
  /** Per-request timeout in milliseconds. */
  requestTimeoutMs?: number
  /** Initial reconnect delay; doubles up to maxReconnectDelayMs. */
  reconnectDelayMs?: number
  /** Upper bound for the reconnect backoff. */
  maxReconnectDelayMs?: number
}

const DEFAULT_REQUEST_TIMEOUT_MS = 10_000
const DEFAULT_RECONNECT_DELAY_MS = 1_000
const DEFAULT_MAX_RECONNECT_DELAY_MS = 15_000

/**
 * Thin, reconnecting client for Moonraker's JSON-RPC WebSocket API.
 *
 * Responsibilities:
 *  - frame JSON-RPC requests and correlate responses by id;
 *  - surface connection-state transitions to the UI;
 *  - fan out `notify_*` notifications to method-scoped listeners;
 *  - transparently restore subscriptions after a reconnect.
 *
 * It deliberately knows nothing about specific printer objects or widgets — that
 * domain logic lives in the store and feature widgets, keeping this class reusable.
 */
export class MoonrakerClient {
  private socket: WebSocket | null = null
  private readonly url: string
  private readonly requestTimeoutMs: number
  private readonly reconnectDelayMs: number
  private readonly maxReconnectDelayMs: number

  private nextId = 1
  private readonly pending = new Map<number, PendingCall>()
  private readonly stateListeners = new Set<StateListener>()
  private readonly notificationListeners = new Map<string, Set<NotificationListener>>()
  private subscriptions: Record<string, string[] | null> = {}

  private reconnectDelay: number
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private shouldReconnect = true
  private currentState: ConnectionState = 'idle'

  constructor(options: MoonrakerClientOptions = {}) {
    this.url = options.url ?? resolveEndpoints().wsUrl
    this.requestTimeoutMs = options.requestTimeoutMs ?? DEFAULT_REQUEST_TIMEOUT_MS
    this.reconnectDelayMs = options.reconnectDelayMs ?? DEFAULT_RECONNECT_DELAY_MS
    this.maxReconnectDelayMs = options.maxReconnectDelayMs ?? DEFAULT_MAX_RECONNECT_DELAY_MS
    this.reconnectDelay = this.reconnectDelayMs
  }

  /** The current connection state. */
  get state(): ConnectionState {
    return this.currentState
  }

  /** Opens the WebSocket. Safe to call repeatedly; ignored while already open. */
  connect(): void {
    if (this.socket && this.socket.readyState <= WebSocket.OPEN) return
    this.shouldReconnect = true
    this.open()
  }

  /** Closes the socket and stops reconnecting. */
  disconnect(): void {
    this.shouldReconnect = false
    this.clearReconnectTimer()
    this.socket?.close()
    this.socket = null
    this.setState('closed')
  }

  /** Subscribes to connection-state changes. Returns an unsubscribe function. */
  onStateChange(listener: StateListener): () => void {
    this.stateListeners.add(listener)
    return () => this.stateListeners.delete(listener)
  }

  /**
   * Registers a listener for a Moonraker notification method
   * (e.g. "notify_status_update"). Returns an unsubscribe function.
   */
  onNotification(method: string, listener: NotificationListener): () => void {
    const listeners = this.notificationListeners.get(method) ?? new Set<NotificationListener>()
    listeners.add(listener)
    this.notificationListeners.set(method, listeners)
    return () => listeners.delete(listener)
  }

  /** Issues a JSON-RPC request and resolves with its `result`. */
  call<T = unknown>(method: string, params?: Record<string, unknown>): Promise<T> {
    return new Promise<T>((resolve, reject) => {
      if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
        reject(new Error(`Cannot call "${method}": socket is not open`))
        return
      }

      const id = this.nextId++
      const timer = setTimeout(() => {
        this.pending.delete(id)
        reject(new Error(`Request "${method}" timed out after ${this.requestTimeoutMs}ms`))
      }, this.requestTimeoutMs)

      this.pending.set(id, { resolve: resolve as (value: unknown) => void, reject, timer })

      const payload = { jsonrpc: '2.0', method, id, ...(params ? { params } : {}) }
      this.socket.send(JSON.stringify(payload))
    })
  }

  /**
   * Subscribes to a set of printer objects. `objects` maps an object name to the
   * fields to watch (or null for all fields), per Moonraker's API. The merged
   * subscription set is remembered and re-applied automatically after reconnects.
   */
  async subscribeObjects(
    objects: Record<string, string[] | null>,
  ): Promise<Record<string, Record<string, unknown>>> {
    this.subscriptions = { ...this.subscriptions, ...objects }
    const result = await this.call<{ status: Record<string, Record<string, unknown>> }>(
      'printer.objects.subscribe',
      { objects: this.subscriptions },
    )
    return result.status
  }

  // --- internals ---------------------------------------------------------

  private open(): void {
    this.setState(this.currentState === 'idle' ? 'connecting' : 'reconnecting')

    const socket = new WebSocket(this.url)
    this.socket = socket

    socket.addEventListener('open', () => {
      this.reconnectDelay = this.reconnectDelayMs
      this.setState('connected')
      void this.resubscribe()
    })
    socket.addEventListener('message', (event) => this.handleMessage(event.data))
    socket.addEventListener('close', () => this.handleClose())
    socket.addEventListener('error', () => this.setState('error'))
  }

  private async resubscribe(): Promise<void> {
    if (Object.keys(this.subscriptions).length === 0) return
    try {
      await this.call('printer.objects.subscribe', { objects: this.subscriptions })
    } catch (error) {
      // Non-fatal: the next reconnect will retry.
      console.error('[moonraker] failed to restore subscriptions', error)
    }
  }

  private handleMessage(data: unknown): void {
    if (typeof data !== 'string') return

    let message: JsonRpcMessage
    try {
      message = JSON.parse(data) as JsonRpcMessage
    } catch {
      console.warn('[moonraker] dropped a non-JSON frame')
      return
    }

    if ('id' in message && message.id !== null && ('result' in message || 'error' in message)) {
      this.resolvePending(message as JsonRpcSuccess | JsonRpcError)
      return
    }
    if ('method' in message) {
      this.dispatchNotification(message as JsonRpcNotification)
    }
  }

  private resolvePending(message: JsonRpcSuccess | JsonRpcError): void {
    const id = message.id as number
    const call = this.pending.get(id)
    if (!call) return

    this.pending.delete(id)
    clearTimeout(call.timer)

    if ('error' in message) {
      call.reject(new Error(message.error.message))
    } else {
      call.resolve(message.result)
    }
  }

  private dispatchNotification(message: JsonRpcNotification): void {
    const listeners = this.notificationListeners.get(message.method)
    if (!listeners) return
    for (const listener of listeners) listener(message.params)
  }

  private handleClose(): void {
    this.socket = null
    this.rejectAllPending(new Error('socket closed'))

    if (!this.shouldReconnect) {
      this.setState('closed')
      return
    }
    this.setState('reconnecting')
    this.scheduleReconnect()
  }

  private scheduleReconnect(): void {
    this.clearReconnectTimer()
    this.reconnectTimer = setTimeout(() => {
      this.reconnectDelay = Math.min(this.reconnectDelay * 2, this.maxReconnectDelayMs)
      this.open()
    }, this.reconnectDelay)
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
  }

  private rejectAllPending(reason: Error): void {
    for (const call of this.pending.values()) {
      clearTimeout(call.timer)
      call.reject(reason)
    }
    this.pending.clear()
  }

  private setState(state: ConnectionState): void {
    if (this.currentState === state) return
    this.currentState = state
    for (const listener of this.stateListeners) listener(state)
  }
}
