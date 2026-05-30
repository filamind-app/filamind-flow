/** Minimal JSON-RPC 2.0 types for Moonraker's WebSocket API. */
export interface JsonRpcRequest {
  jsonrpc: '2.0'
  method: string
  params?: Record<string, unknown>
  id: number
}

export interface JsonRpcSuccess<T = unknown> {
  jsonrpc: '2.0'
  result: T
  id: number
}

export interface JsonRpcError {
  jsonrpc: '2.0'
  error: { code: number; message: string; data?: unknown }
  id: number | null
}

export interface JsonRpcNotification<T = unknown> {
  jsonrpc: '2.0'
  method: string
  params?: T
}

export type JsonRpcMessage = JsonRpcSuccess | JsonRpcError | JsonRpcNotification

/** Connection lifecycle states surfaced to the UI. */
export type ConnectionState =
  | 'idle'
  | 'connecting'
  | 'connected'
  | 'reconnecting'
  | 'error'
  | 'closed'

/** A Moonraker "printer objects" status payload is an open-ended map. */
export type PrinterObjectStatus = Record<string, Record<string, unknown>>
