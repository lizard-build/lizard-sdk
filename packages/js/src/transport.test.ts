import { fileURLToPath } from 'node:url'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { PlatformClient } from './platform/client'
import { ServicesAPI } from './platform/services'
import { Lizard, LizardCLI, Sandbox } from './index'

const opts = { apiKey: 'liz_test', apiUrl: 'https://test.invalid' }
afterEach(() => { vi.unstubAllGlobals() })

function chunks(text: string, cancel = vi.fn()) {
  const bytes = new TextEncoder().encode(text)
  let i = 0
  return new ReadableStream({ pull(controller) { if (i < bytes.length) controller.enqueue(bytes.slice(i, ++i)); else controller.close() }, cancel })
}
describe('SSE and HTTP transport', () => {
  it('handles CRLF, multiline data and split UTF-8; preserves event and id', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(chunks(': ping\r\nid: 7\r\nevent: stdout\r\ndata: привет\r\ndata: world\r\n\r\nevent: exit\r\ndata:{"exitCode":0}\r\n\r\n'))))
    const result = []
    for await (const event of new PlatformClient(opts).events('/stream')) result.push(event)
    expect(result).toEqual([{ event: 'stdout', data: 'привет\nworld', id: '7' }, { event: 'exit', data: '{"exitCode":0}', id: '7' }])
  })
  it('cancels the reader when the caller stops consuming', async () => {
    const cancel = vi.fn()
    vi.stubGlobal('fetch', vi.fn(async () => new Response(chunks('data: one\n\ndata: two\n\n', cancel))))
    for await (const _ of new PlatformClient(opts).events('/stream')) break
    expect(cancel).toHaveBeenCalledOnce()
  })
  it('does not report a truncated exec as success', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('data: {"stream":"stdout","line":"partial"}\n\n')))
    await expect(new ServicesAPI(new PlatformClient(opts)).exec('s', 'hi')).rejects.toThrow('without exit status')
  })
  it('propagates remote stream errors', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('event: error\ndata: command failed\n\n')))
    await expect(new ServicesAPI(new PlatformClient(opts)).exec('s', 'hi')).rejects.toThrow('command failed')
  })
  it.each(['post', 'patch', 'put', 'delete'] as const)('accepts empty successful %s responses', async method => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(null, { status: 204 })))
    expect(await new PlatformClient(opts)[method]('/resource', {})).toBeUndefined()
  })
  it('does not retry a 409 mutation', async () => {
    const fetch = vi.fn(async () => new Response('{"error":"revision mismatch"}', { status: 409 }))
    vi.stubGlobal('fetch', fetch)
    await expect(new PlatformClient(opts).post('/apply', {})).rejects.toThrow('revision mismatch')
    expect(fetch).toHaveBeenCalledOnce()
  })
  it('preserves zero sandbox lifetime', async () => {
    const fetch = vi.fn(async (_url: unknown, _init?: RequestInit) => new Response('{"sandboxId":"s1"}'))
    vi.stubGlobal('fetch', fetch)
    await Sandbox.create('base', { ...opts, projectId: 'p1', timeoutMs: 0 })
    expect(JSON.parse(String(fetch.mock.calls[0][1]?.body))).toMatchObject({ timeoutMs: 0 })
  })
  it('rejects lossy binary file writes before sending', async () => {
    const fetch = vi.fn(); vi.stubGlobal('fetch', fetch)
    await expect(new Sandbox({ sandboxId: 's', ...opts }).fs.write('/tmp/data', new Uint8Array([255]))).rejects.toThrow()
    expect(fetch).not.toHaveBeenCalled()
  })
  it('does not move a secret across projects', async () => {
    const fetch = vi.fn(async () => new Response('{"name":"api","projectId":"other"}'))
    vi.stubGlobal('fetch', fetch)
    await expect(new Lizard(opts).secrets.set('p1', { key: 'K', value: 'V', serviceId: 's' })).rejects.toThrow('does not belong')
    expect(fetch).toHaveBeenCalledOnce()
  })
})
const executable = fileURLToPath(new URL('../../../tests/fixtures/fake-cli.cjs', import.meta.url))
describe('optional CLI adapter', () => {
  it('passes shell syntax as literal arguments, including after --', async () => {
    const args = ['run', '--', 'printf', '$(false); echo bad', 'two words']
    const result = await new LizardCLI({ executable }).run(args, { stdin: 'KEY=value\n' })
    expect(result.code).toBe(0)
    expect(result.events).toEqual([{ args: ['--json', ...args], input: 'KEY=value\n' }])
  })
  it('preserves nonzero exit status', async () => {
    expect((await new LizardCLI({ executable }).run(['fail'])).code).toBe(3)
  })
  it('uses explicit cents and request ID for x402, without shell or automatic retries', async () => {
    const result = await new Lizard(opts).billing.payX402(2000, { maxTotalCents: 2100, requestId: 'request-1', executable })
    expect(result).toEqual({ args: ['--json', 'credits', 'topup', '20.00', '--method', 'x402', '--max-total', '21.00', '--yes', '--request-id', 'request-1'], input: '' })
  })
})

describe('deploy completion', () => {
  it('fails a new build even if the old service is still running', async () => {
    const fetch = vi.fn(async () => new Response('{"status":"failed"}'))
    vi.stubGlobal('fetch', fetch)
    const { DeployHandle } = await import('./platform/services')
    await expect(new DeployHandle(new PlatformClient(opts), 's1', 'b1').wait()).rejects.toThrow('Deploy failed')
    expect(fetch).toHaveBeenCalledOnce()
  })
  it('does not accept the old running service while the new build is pending', async () => {
    const fetch = vi.fn(async (url: string) => new Response(JSON.stringify(url.endsWith('/b1') ? { status: 'building' } : { status: 'running', deployStatus: 'idle' })))
    vi.stubGlobal('fetch', fetch)
    const { DeployHandle } = await import('./platform/services')
    await expect(new DeployHandle(new PlatformClient(opts), 's1', 'b1').wait({ timeoutMs: 5, pollMs: 1 })).rejects.toThrow('did not complete')
  })
})

it('reports config side-effect failure without retrying the saved config', async () => {
  const response = { revision: 8, services: [], addons: [], sideEffectFailures: [{ action: 'restart', error: 'unavailable' }] }
  const fetch = vi.fn(async () => new Response(JSON.stringify(response)))
  vi.stubGlobal('fetch', fetch)
  const { ConfigApplyError } = await import('./errors')
  await expect(new Lizard(opts).projects.apply('p1', {})).rejects.toBeInstanceOf(ConfigApplyError)
  expect(fetch).toHaveBeenCalledOnce()
})
