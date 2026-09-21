/**
 * A sandbox is billed per project, so the SDK must never send a create request
 * without one. These cover the resolution itself — no network, fetch is stubbed.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ConnectionConfig } from './config'
import { LizardError } from './errors'
import { resolveProjectId, resolveRequiredProjectId } from './project'
import { Lizard } from './lizard'

const PROJECTS = [
  { id: 'p_abc', name: 'My Project', slug: 'my-project-x1' },
  { id: 'p_def', name: 'Other', slug: 'other-y2' },
]

// Each test uses a distinct ref so the module-level resolution cache — shared
// per (apiUrl, ref) — can't carry a value between them.
let n = 0
const uniqueApiUrl = () => `https://api.test-${n++}.invalid`
const config = () => new ConnectionConfig({ apiKey: 'liz_test', apiUrl: uniqueApiUrl() })

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(JSON.stringify(PROJECTS), { status: 200 }))
  )
})
afterEach(() => vi.unstubAllGlobals())

describe('resolveProjectId', () => {
  it('matches on id, slug, and name, ignoring case', async () => {
    const c = config()
    expect(await resolveProjectId('p_abc', c)).toBe('p_abc')
    expect(await resolveProjectId('my-project-x1', c)).toBe('p_abc')
    expect(await resolveProjectId('My Project', c)).toBe('p_abc')
    expect(await resolveProjectId('MY PROJECT', c)).toBe('p_abc')
  })

  it('throws on an unknown project and lists what is available', async () => {
    await expect(resolveProjectId('nope', config())).rejects.toThrow(/not found.*my-project-x1/s)
  })

  it('caches so repeated creates do not re-list projects', async () => {
    const c = config()
    await resolveProjectId('my-project-x1', c)
    await resolveProjectId('my-project-x1', c)
    expect(fetch).toHaveBeenCalledTimes(1)
  })
})

describe('resolveRequiredProjectId', () => {
  it('prefers an exact projectId and skips the network', async () => {
    expect(await resolveRequiredProjectId({ projectId: 'p_zzz' }, config())).toBe('p_zzz')
    expect(fetch).not.toHaveBeenCalled()
  })

  it('resolves a project reference', async () => {
    expect(await resolveRequiredProjectId({ project: 'other-y2' }, config())).toBe('p_def')
  })

  it('refuses to create without a project', async () => {
    await expect(resolveRequiredProjectId(undefined, config())).rejects.toThrow(LizardError)
    await expect(resolveRequiredProjectId({}, config())).rejects.toThrow(/project is required/i)
  })
})

describe('Lizard', () => {
  it('constructs without a project, and defers the error to the sandbox call', async () => {
    // `project` is optional since the platform namespace landed: a client that only
    // manages workspaces, keys or projects has no sandbox to bill and should not have
    // to invent a project to be constructed. The requirement moved to the point where
    // it actually matters — anything that creates or resolves a sandbox.
    const lizard = new Lizard({ apiKey: 'liz_test', apiUrl: uniqueApiUrl() })
    expect(lizard.workspaces).toBeDefined()
    await expect(lizard.projectId()).rejects.toThrow(/no project set/i)
    await expect(lizard.create('base')).rejects.toThrow(LizardError)
  })

  it('resolves its project reference to an id', async () => {
    const lizard = new Lizard({ project: 'my-project-x1', apiKey: 'liz_test', apiUrl: uniqueApiUrl() })
    expect(await lizard.projectId()).toBe('p_abc')
  })
})
