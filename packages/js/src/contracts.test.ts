import { readFileSync } from 'node:fs'
import { describe, it, expect, vi, afterEach } from 'vitest'
import { Lizard, Sandbox, Volume } from './index'

const cases: any[] = JSON.parse(readFileSync(new URL('../../../tests/contracts/platform.json', import.meta.url), 'utf8'))
const config = { apiKey: 'liz_contract_test', apiUrl: 'https://contract.invalid' }
const bytes = new Uint8Array([0, 255, 31, 139])
function hydrate(value: any): any {
  if (value === '__BYTES__') return bytes
  if (Array.isArray(value)) return value.map(hydrate)
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, hydrate(v)]))
  return value
}
function address(path: string) {
  const url = new URL(path, config.apiUrl)
  return { path: url.pathname, query: [...url.searchParams].sort() }
}
afterEach(() => { vi.unstubAllGlobals() })
describe('CLI/backend wire contracts (shared with Python)', () => {
  it.each(cases)('$name', async test => {
    let index = 0
    vi.stubGlobal('fetch', vi.fn(async (url: string, init: RequestInit = {}) => {
      const want = test.requests[index++]
      expect(want, `unexpected request ${url}`).toBeDefined()
      expect(address(url)).toEqual(address(want.path))
      expect(init.method ?? 'GET').toBe(want.method)
      expect(new Headers(init.headers).get('X-API-Key')).toBe(config.apiKey)
      if ('body' in want) expect(init.body ? JSON.parse(String(init.body)) : undefined).toEqual(want.body)
      if (want.rawBody) {
        expect([...new Uint8Array(await new Response(init.body).arrayBuffer())]).toEqual(want.rawBody)
        expect(new Headers(init.headers).get('Content-Type')).toBe(want.contentType)
      }
      return new Response(want.status === 204 ? null : want.binaryResponse ? new Uint8Array(want.binaryResponse) : want.rawResponse ?? want.stream ?? JSON.stringify(want.response), {
        status: want.status ?? 200, headers: { 'Content-Type': want.stream ? 'text/event-stream' : 'application/json' },
      })
    }))
    const client = new Lizard(config)
    const root: any = Object.assign(client, {
      sandbox: new Sandbox({ sandboxId: 'sb1', ...config }),
      Volume: {
        create: (p: string, n: string) => Volume.create(p, n, config),
        getOrCreate: (p: string, n: string) => Volume.getOrCreate(p, n, config),
        get: (p: string, n: string) => Volume.get(p, n, config),
        list: (p: string) => Volume.list(p, config),
        delete: (p: string, n: string) => Volume.delete(p, n, config),
      },
      Sandbox: {
        create: (template: string, opts = {}) => Sandbox.create(template, { ...opts, ...config }),
        connect: (id: string) => Sandbox.connect(id, config),
        list: (opts = {}) => Sandbox.list({ ...opts, ...config }),
        snapshots: (id: string) => Sandbox.snapshots(id, config),
        restore: (id: string) => Sandbox.restore(id, config),
        getSnapshot: (id: string) => Sandbox.getSnapshot(id, config),
        setSnapshotWarmPool: (id: string, count: number) => Sandbox.setSnapshotWarmPool(id, count, config),
        pauseSnapshot: (id: string) => Sandbox.pauseSnapshot(id, config),
        resumeSnapshot: (id: string) => Sandbox.resumeSnapshot(id, config),
        deleteSnapshot: (id: string) => Sandbox.deleteSnapshot(id, config),
      },
    })
    const execute = async () => {
      const parts = test.ts.path.split('.')
      const receiver = parts.slice(0, -1).reduce((obj: any, part: string) => obj[part], root)
      const result = await receiver[parts[parts.length - 1]](...hydrate(test.ts.args))
      if (result?.[Symbol.asyncIterator]) { const events = []; for await (const event of result) events.push(event); return events }
      return result
    }
    if (test.error) await expect(execute()).rejects.toThrow(test.error)
    else {
      const result = await execute()
      if (test.name === 'services.exec') expect(result).toEqual({ stdout: 'hi\n', stderr: 'oops\n', exitCode: 2 })
      if (test.name === 'metrics.all') expect(result).toMatchObject({ networkRx: [{ t: 100, value: 1 }, { t: 200, value: 2 }] })
      if (test.name === 'domains.list') expect(result).toMatchObject([{ domain: 'example.test', live: true }, { domain: 'pending.test', txtValue: 'proof', verified: false }])
      if (test.name === 'services.logs') expect(result).toHaveLength(1)
    }
    expect(index).toBe(test.requests.length)
  })
})
