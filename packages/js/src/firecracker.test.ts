/**
 * The Firecracker sandbox contract: pid events, binary writes, port tokens, fork,
 * and the exec-based code runner. fetch is stubbed — no network.
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { Sandbox } from './sandbox'
import { CodeSandbox } from './code-interpreter'
import { RUNNER_SOURCE } from './code-interpreter/runner'
import { ConflictError, LizardError } from './errors'

const opts = { apiKey: 'liz_test', apiUrl: 'https://api.fc.invalid' }

afterEach(() => { vi.unstubAllGlobals() })

const sse = (events: string[]) => new Response(events.map(e => e + '\n\n').join(''), {
  headers: { 'Content-Type': 'text/event-stream' },
})
const body = (fetch: { mock: { calls: any[][] } }, i = 0) => JSON.parse(String(fetch.mock.calls[i][1]?.body))

describe('exec onPid', () => {
  it('asks for the pid event and hands the pid over', async () => {
    const fetch = vi.fn(async (_url: unknown, _init?: RequestInit) => sse([
      ': operation x',
      'data: {"pid":1024}',
      'data: {"stream":"stdout","line":"a"}',
      'event: exit\ndata: {"exitCode":4}',
    ]))
    vi.stubGlobal('fetch', fetch)
    const pids: number[] = []
    const r = await new Sandbox({ sandboxId: 's', ...opts }).process.exec('echo a; exit 4', { onPid: p => pids.push(p) })
    expect(body(fetch).pidEvent).toBe(true)
    expect(pids).toEqual([1024])
    expect(r).toMatchObject({ stdout: 'a', exitCode: 4 })
  })

  it('does not ask for it without onPid', async () => {
    const fetch = vi.fn(async (_url: unknown, _init?: RequestInit) => sse(['data: {"stream":"stdout","line":"a"}', 'event: exit\ndata: {"exitCode":0}']))
    vi.stubGlobal('fetch', fetch)
    await new Sandbox({ sandboxId: 's', ...opts }).process.exec('echo a', { onStdout: () => {} })
    expect(body(fetch).pidEvent).toBeUndefined()
  })
})

describe('ports', () => {
  it('getHost keeps the access token; exposePort returns it', async () => {
    const answer = { hostname: 's-3000.sandbox.eu.onlizard.com', url: 'https://s-3000.sandbox.eu.onlizard.com/?lizard_token=tok', port: 3000, accessToken: 'tok' }
    vi.stubGlobal('fetch', vi.fn(async (_url: unknown, _init?: RequestInit) => new Response(JSON.stringify(answer))))
    const sb = new Sandbox({ sandboxId: 's', ...opts })
    expect(await sb.getHost(3000)).toBe(answer.hostname)
    expect(sb.accessToken).toBe('tok')
    expect(await sb.exposePort(3000)).toEqual(answer)
  })
})

describe('fork', () => {
  it('returns sandbox handles of the same class, and per-copy errors', async () => {
    const fetch = vi.fn(async (_url: unknown, _init?: RequestInit) => new Response(JSON.stringify([
      { sandbox: { sandboxId: 'f1', status: 'running', runtime: 'firecracker' } },
      { error: 'Sandbox limit reached' },
    ]), { status: 201 }))
    vi.stubGlobal('fetch', fetch)
    const forks = await new CodeSandbox({ sandboxId: 's', ...opts }).fork({ count: 2 })
    expect(body(fetch)).toEqual({ count: 2, timeoutMs: 0 })
    expect(forks[0].sandbox).toBeInstanceOf(CodeSandbox)
    expect(forks[0].sandbox?.sandboxId).toBe('f1')
    expect(forks[0].info?.runtime).toBe('firecracker')
    expect(forks[1]).toEqual({ error: 'Sandbox limit reached' })
  })

  it('surfaces the volume conflict', async () => {
    vi.stubGlobal('fetch', vi.fn(async (_url: unknown, _init?: RequestInit) => new Response('{"error":"A sandbox with a volume attached cannot be forked"}', { status: 409 })))
    await expect(new Sandbox({ sandboxId: 's', ...opts }).fork()).rejects.toBeInstanceOf(ConflictError)
  })
})

describe('CodeSandbox', () => {
  it('boots the interpreter template', async () => {
    const fetch = vi.fn(async (_url: unknown, _init?: RequestInit) => new Response('{"sandboxId":"c1"}'))
    vi.stubGlobal('fetch', fetch)
    const sb = await CodeSandbox.create({ projectId: 'p1', ...opts })
    expect(body(fetch).template).toBe('interpreter')
    expect(sb).toBeInstanceOf(CodeSandbox)
  })

  it('runs code through exec and builds the Execution, joining split lines', async () => {
    const result = JSON.stringify({ type: 'result', mime: 'image/png', data: 'A'.repeat(50) })
    const parts = [result.slice(0, 20), result.slice(20, 40), result.slice(40)]
    const line = (o: unknown) => `data: ${JSON.stringify({ stream: 'stdout', line: JSON.stringify(o) })}`
    const fetch = vi.fn(async (_url: unknown, _init?: RequestInit) => sse([
      line({ type: 'stdout', data: 'hi\n' }),
      line({ type: 'stderr', data: 'warn\n' }),
      ...parts.map((p, i) => line({ type: 'part', data: p, end: i === parts.length - 1 })),
      line({ type: 'error', name: 'ZeroDivisionError', message: 'division by zero', traceback: 'tb' }),
      line({ type: 'done', execution_count: 3 }),
      'event: exit\ndata: {"exitCode":0}',
    ]))
    vi.stubGlobal('fetch', fetch)
    const out: string[] = []
    const run = await new CodeSandbox({ sandboxId: 'c1', ...opts }).runCode('1/0', { envs: { A: '1' }, onStdout: d => out.push(d) })
    const sent = body(fetch)
    expect(sent.cmd.slice(0, 2)).toEqual(['python3', '-c'])
    expect(sent.cmd[2]).toBe(RUNNER_SOURCE)
    expect(JSON.parse(Buffer.from(sent.cmd[3], 'base64').toString())).toEqual({ action: 'run', code: '1/0', envs: { A: '1' }, timeout: 60, language: 'python' })
    expect(run.stdout).toBe('hi\n')
    expect(run.stderr).toBe('warn\n')
    expect(out).toEqual(['hi\n'])
    expect(run.results).toEqual([{ type: 'result', mime: 'image/png', data: 'A'.repeat(50) }])
    expect(run.error?.name).toBe('ZeroDivisionError')
    expect(run.executionCount).toBe(3)
  })

  it('throws when the runner cannot run', async () => {
    vi.stubGlobal('fetch', vi.fn(async (_url: unknown, _init?: RequestInit) => sse([
      'data: {"stream":"stderr","line":"sh: python3: not found"}',
      'event: exit\ndata: {"exitCode":127}',
    ])))
    await expect(new CodeSandbox({ sandboxId: 'c1', ...opts }).runCode('1')).rejects.toBeInstanceOf(LizardError)
  })

  it('keeps the runner identical to the Python SDK copy', () => {
    const py = readFileSync(join(__dirname, '../../python/lizard/code_interpreter/_runner.py'), 'utf8')
    const src = py.slice(py.indexOf('r"""') + 4, py.lastIndexOf('"""'))
    expect(src).toBe(RUNNER_SOURCE)
  })
})
