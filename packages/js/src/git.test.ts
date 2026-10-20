/** lizard.git with fetch stubbed: where requests go and what they carry. No network. */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { Lizard } from './lizard'
import { NotFoundError } from './errors'

const opts = { apiKey: 'liz_test', apiUrl: 'https://api.invalid', gitUrl: 'https://git.invalid/' }

function stub(responses: Array<{ status?: number; body: unknown }>) {
  const calls: Array<{ url: string; method: string; headers: Record<string, string>; body: any }> = []
  let i = 0
  vi.stubGlobal('fetch', vi.fn(async (url: any, init?: any) => {
    calls.push({ url: String(url), method: init?.method ?? 'GET', headers: init?.headers ?? {}, body: typeof init?.body === 'string' ? JSON.parse(init.body) : init?.body })
    const r = responses[Math.min(i++, responses.length - 1)]
    const text = JSON.stringify(r.body)
    return new Response(text, { status: r.status ?? 200, headers: { 'content-type': 'application/json' } })
  }))
  return calls
}

afterEach(() => { vi.unstubAllGlobals() })

describe('lizard.git', () => {
  it('sends the API key to Lizard Git, not the platform', async () => {
    const calls = stub([{ body: { login: 'me' } }])
    await new Lizard(opts).git.me()
    expect(calls[0].url).toBe('https://git.invalid/api/session')
    expect(calls[0].headers['X-API-Key']).toBe('liz_test')
  })

  it('names repositories owner/name', async () => {
    const calls = stub([{ body: { items: [], open: 0, closed: 0 } }])
    await new Lizard(opts).git.pulls.list('me/app', { state: 'all' })
    expect(calls[0].url).toBe('https://git.invalid/api/repos/me/app/issues?state=all&pulls=1')
    expect(() => new Lizard(opts).git.repos.get('noslash')).toThrow(/owner\/name/)
  })

  it('commits files with the idempotency key as a header', async () => {
    const calls = stub([{ status: 201, body: { sha: 'a'.repeat(40), branch: 'main' } }])
    await new Lizard(opts).git.repos.commitFiles('me/app', {
      branch: 'main', message: 'm', expect: 'b'.repeat(40), idempotencyKey: 'k1', files: [{ path: 'a.txt', content: 'x' }],
    })
    expect(calls[0].method).toBe('POST')
    expect(calls[0].url).toBe('https://git.invalid/api/repos/me/app/commits')
    expect(calls[0].headers['Idempotency-Key']).toBe('k1')
    expect(calls[0].body).toEqual({ branch: 'main', message: 'm', expect: 'b'.repeat(40), files: [{ path: 'a.txt', content: 'x' }] })
  })

  it('maps errors to the SDK error classes', async () => {
    stub([{ status: 404, body: { error: 'no such repository' } }])
    await expect(new Lizard(opts).git.repos.get('me/gone')).rejects.toBeInstanceOf(NotFoundError)
  })

  it('reads a pull request\'s checks at its head commit', async () => {
    const calls = stub([
      { body: { issue: { number: 3 }, comments: [], pull: { headSha: 'c'.repeat(40) } } },
      { body: { sha: 'c'.repeat(40), state: 'success', statuses: [], total_count: 0 } },
    ])
    const st = await new Lizard(opts).git.pulls.checks('me/app', 3)
    expect(calls[1].url).toBe(`https://git.invalid/api/repos/me/app/commits/${'c'.repeat(40)}/status`)
    expect(st.state).toBe('success')
  })

  it('marks all notifications read when given no ids', async () => {
    const calls = stub([{ body: { ok: true } }])
    await new Lizard(opts).git.notifications.markRead()
    expect(calls[0].body).toEqual({ all: true })
  })

  it('builds clone URLs, with the key only when asked', () => {
    const git = new Lizard(opts).git
    expect(git.repos.cloneUrl('me/app')).toBe('https://git.invalid/me/app.git')
    expect(git.repos.cloneUrl('me/app', { withKey: true })).toBe('https://lizard:liz_test@git.invalid/me/app.git')
  })
})

describe('lizard.git path safety', () => {
  it('refuses . and .. in repositories, branches and paths', async () => {
    const git = new Lizard(opts).git
    expect(() => git.repos.get('../user')).toThrow()
    await expect(async () => git.repos.deleteBranch('me/r', '../../../../user/tokens/5')).rejects.toThrow(/bad path/)
    await expect(async () => git.repos.raw('me/r', '../../x/.env', 'main')).rejects.toThrow(/bad path/)
  })
})
