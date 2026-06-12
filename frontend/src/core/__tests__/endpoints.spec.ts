import { afterEach, describe, expect, it, vi } from 'vitest'

import { mountPrefix, resolveEndpoints } from '../moonraker/config'

function atLocation(href: string): void {
  const url = new URL(href)
  vi.stubGlobal('window', {
    location: {
      origin: url.origin,
      protocol: url.protocol,
      host: url.host,
      pathname: url.pathname,
    },
  })
}

afterEach(() => vi.unstubAllGlobals())

describe('mountPrefix', () => {
  it('is empty at the origin root', () => {
    atLocation('http://printer.local:8090/')
    expect(mountPrefix()).toBe('')
  })

  it('is empty when the document is index.html at root', () => {
    atLocation('http://printer.local:8090/index.html')
    expect(mountPrefix()).toBe('')
  })

  it('is the subpath when proxied under one', () => {
    atLocation('https://host.example.com/filamind/')
    expect(mountPrefix()).toBe('/filamind')
  })

  it('handles a subpath index.html', () => {
    atLocation('https://host.example.com/filamind/index.html')
    expect(mountPrefix()).toBe('/filamind')
  })
})

describe('resolveEndpoints', () => {
  it('calls the panel at the origin root by default', () => {
    atLocation('http://printer.local:8090/')
    const e = resolveEndpoints()
    expect(e.backendUrl).toBe('http://printer.local:8090')
    expect(e.httpUrl).toBe('http://printer.local:8090')
    expect(e.wsUrl).toBe('ws://printer.local:8090/websocket')
  })

  it('prefixes every endpoint with the subpath when mounted under one (wss on https)', () => {
    atLocation('https://host.example.com/filamind/')
    const e = resolveEndpoints()
    expect(e.backendUrl).toBe('https://host.example.com/filamind')
    expect(e.httpUrl).toBe('https://host.example.com/filamind')
    expect(e.wsUrl).toBe('wss://host.example.com/filamind/websocket')
  })
})
