import { afterEach, describe, expect, it, vi } from 'vitest'
import { Sandbox, LizardError, PlatformClient } from './index'

const opts = { apiKey: 'liz_test', apiUrl: 'https://test.invalid' }
afterEach(() => { vi.unstubAllGlobals() })

function stub(body: unknown = { stdout: '', stderr: '', exitCode: 0 }, status = 200) {
  const calls: Array<{ url: string; init: RequestInit; body: any }> = []
  vi.stubGlobal('fetch', vi.fn(async (url: string, init: RequestInit = {}) => {
    calls.push({ url: String(url), init, body: init.body ? JSON.parse(String(init.body)) : undefined })
    return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
  }))
  return calls
}

describe('fs.makeDir', () => {
  it('sends an argv, so shell syntax in the path stays literal', async () => {
    const calls = stub()
    const path = '/tmp/$(id)/`id`/$HOME'
    await new Sandbox({ sandboxId: 'sb1', ...opts }).fs.makeDir(path)
    expect(calls[0].url).toBe('https://test.invalid/api/sandboxes/sb1/exec')
    expect(calls[0].body.cmd).toEqual(['mkdir', '-p', '--', path])
  })
  it('throws when mkdir exits non-zero', async () => {
    stub({ stdout: '', stderr: 'mkdir: Permission denied', exitCode: 1 })
    await expect(new Sandbox({ sandboxId: 'sb1', ...opts }).fs.makeDir('/root/x')).rejects.toThrow(LizardError)
  })
})

describe('requests carrying the API key', () => {
  it('never follow redirects', async () => {
    const calls = stub({ stdout: '', stderr: '', exitCode: 0 })
    const sb = new Sandbox({ sandboxId: 'sb1', ...opts })
    await sb.process.exec('true')
    await sb.fs.makeDir('/x')
    await new PlatformClient(opts).get('/api/projects')
    expect(calls.length).toBe(3)
    for (const c of calls) expect(c.init.redirect).toBe('error')
  })
})

describe('ids in API paths', () => {
  it('are URL-encoded', async () => {
    const calls = stub()
    await new Sandbox({ sandboxId: '../admin?x=1#', ...opts }).process.exec('true')
    expect(calls[0].url).toBe('https://test.invalid/api/sandboxes/..%2Fadmin%3Fx%3D1%23/exec')
  })
})
