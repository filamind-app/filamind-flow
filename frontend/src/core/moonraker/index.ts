import { MoonrakerClient } from './client'

export * from './client'
export * from './config'
export * from './types'

/** Shared, application-wide Moonraker client instance. */
export const moonraker = new MoonrakerClient()
