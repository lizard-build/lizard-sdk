/**
 * The SDK is meant to reach everything `lizard` the CLI reaches. These cover the
 * pieces that were missing or wrong, with fetch stubbed — no network.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { Lizard } from './lizard'
import { Sandbox } from './sandbox'
import { Volume } from './volume'

const API = 'https://api.parity.invalid'
const opts = { apiKey: 'liz_test', apiUrl: API }

/** Record every request, answer each with the queued response. */
function stubFetch(responses: Array<{ status?: number; body: unknown }>) {
  const calls: Array<{ url: string; method: string; body: any }> = []
  let i = 0
  const fn = vi.fn(async (url: any, init?: any) => {
    calls.push({
      url: String(url),
      method: init?.method ?? 'GET',
      body: init?.body ? JSON.parse(init.body) : undefined,
    })
    const r = responses[Math.min(i++, responses.length - 1)]
    return {
      ok: (r.status ?? 200) < 400,
      status: r.status ?? 200,
      headers: new Map([['content-length', '1']]) as any,
      json: async () => r.body,
      text: async () => JSON.stringify(r.body),
    } as any
  })
  vi.stubGlobal('fetch', fn)
  return calls
}

beforeEach(() => vi.unstubAllGlobals())
afterEach(() => vi.unstubAllGlobals())

describe('region', () => {
  it('sends region on volume create', async () => {
    const calls = stubFetch([{ body: { id: 'v1', name: 'data' } }])
    await Volume.create('p1', 'data', { sizeGb: 3, region: 'us-east-1', ...opts })
    expect(calls[0].body).toMatchObject({ name: 'data', sizeGb: 3, region: 'us-east-1' })
  })

  it('sends region on getOrCreate too', async () => {
    const calls = stubFetch([{ body: { id: 'v1', name: 'data' } }])
    await Volume.getOrCreate('p1', 'data', { region: 'eu-west-lim-a', ...opts })
    expect(calls[0].body).toMatchObject({ region: 'eu-west-lim-a', getOrCreate: true })
  })

  it('sends region on sandbox create', async () => {
    const calls = stubFetch([{ body: { sandboxId: 's1' } }])
    await Sandbox.create('codex', { projectId: 'p1', region: 'us-east-1', ...opts })
    expect(calls[0].body).toMatchObject({ template: 'codex', region: 'us-east-1' })
  })

  it('omits region when not given, so the server can take it from the volume', async () => {
    const calls = stubFetch([{ body: { sandboxId: 's1' } }])
    await Sandbox.create('codex', { projectId: 'p1', volumeName: 'data', ...opts })
    expect(calls[0].body.region).toBeUndefined()
    expect(calls[0].body.volumeName).toBe('data')
  })
})

describe('connect', () => {
  it('reads the sandbox instead of resuming it', async () => {
    // resume is a hard 501 on every sandbox; connecting must not touch it.
    const calls = stubFetch([{ body: { sandboxId: 's1', template: 'codex' } }])
    const sb = await Sandbox.connect('s1', opts)
    expect(sb.sandboxId).toBe('s1')
    expect(calls).toHaveLength(1)
    expect(calls[0].method).toBe('GET')
    expect(calls[0].url).toBe(`${API}/api/sandboxes/s1`)
    expect(calls[0].url).not.toContain('resume')
  })

  it('propagates a 404 rather than returning a dead handle', async () => {
    stubFetch([{ status: 404, body: { error: 'Sandbox not found' } }])
    await expect(Sandbox.connect('gone', opts)).rejects.toThrow()
  })
})

describe('provisioning surfaces', () => {
  it('creates a workspace', async () => {
    const calls = stubFetch([{ body: { id: 'w1', name: 'u-1', slug: 'u-1' } }])
    const ws = await new Lizard(opts).workspaces.create({ name: 'u-1' })
    expect(ws.id).toBe('w1')
    expect(calls[0]).toMatchObject({ url: `${API}/api/workspaces`, method: 'POST', body: { name: 'u-1' } })
  })

  it('deletes a workspace empty-only by default', async () => {
    const calls = stubFetch([{ status: 204, body: {} }])
    await new Lizard(opts).workspaces.delete('w1')
    expect(calls[0].url).toBe(`${API}/api/workspaces/w1?requireEmpty=true`)
  })

  it('only drops that guard when force is explicit', async () => {
    const calls = stubFetch([{ status: 204, body: {} }])
    await new Lizard(opts).workspaces.delete('w1', { force: true })
    expect(calls[0].url).toBe(`${API}/api/workspaces/w1`)
  })

  it('folds workspaces and projects into one scopes array', async () => {
    const calls = stubFetch([{ body: { id: 'k1', name: 'k', key: 'liz_secret', scopes: [] } }])
    const key = await new Lizard(opts).apiKeys.create({ name: 'k', workspaces: ['w1'], projects: ['p1'] })
    expect(key.key).toBe('liz_secret')
    expect(calls[0].body.scopes).toEqual([
      { type: 'workspace', id: 'w1' },
      { type: 'project', id: 'p1' },
    ])
  })

  it('lists regions and reads the balance', async () => {
    stubFetch([{ body: [{ id: 'us-east-1' }] }])
    expect((await new Lizard(opts).regions.list())[0].id).toBe('us-east-1')

    stubFetch([{ body: { plan: 'payg', status: 'active', balanceCents: -5, hourlyRateCents: 22 } }])
    expect((await new Lizard(opts).billing.balance()).hourlyRateCents).toBe(22)
  })

  it('builds the transactions query from its options', async () => {
    const calls = stubFetch([{ body: { items: [], nextCursor: null } }])
    await new Lizard(opts).billing.transactions({ limit: 5, includeUsage: true })
    expect(calls[0].url).toBe(`${API}/api/billing/transactions?limit=5&includeUsage=1`)
  })
})

describe('project-bound volumes', () => {
  it('fills in the project id so callers do not repeat it', async () => {
    const calls = stubFetch([
      { body: [{ id: 'p_abc', name: 'proj', slug: 'proj' }] }, // project resolution
      { body: { id: 'v1', name: 'scratch' } },                  // the volume create
    ])
    const vol = await new Lizard({ ...opts, project: 'proj' }).volumes.getOrCreate('scratch', { sizeGb: 7 })
    expect(vol.volumeId).toBe('v1')
    expect(calls[1].url).toBe(`${API}/api/projects/p_abc/volumes`)
    expect(calls[1].body).toMatchObject({ name: 'scratch', sizeGb: 7, getOrCreate: true })
  })
})
