import { afterEach, describe, expect, it, vi } from 'vitest'
import { Sandbox, ConflictError, TimeoutError } from './index'
const config = { apiKey: 'liz_test', apiUrl: 'https://test.invalid' }
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })
function response(value: unknown) { vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(value), {status: 200}))) }
describe('asynchronous snapshot lifecycle', () => {
  it('returns a ready snapshot', async () => {
    response({id: 'snap-1', status: 'ready', readyCount: 5})
    expect(await Sandbox.waitForSnapshot('snap-1', config)).toMatchObject({readyCount: 5})
  })
  it.each(['failed', 'paused', 'suspended'])('stops waiting when snapshot is %s', async status => {
    response({status, error: 'Cannot restore'})
    await expect(Sandbox.waitForSnapshot('snap-1', config)).rejects.toBeInstanceOf(ConflictError)
  })
  it('bounds snapshot waiting', async () => {
    response({status: 'warming'})
    await expect(Sandbox.waitForSnapshot('snap-1', {...config, waitTimeoutMs: 0})).rejects.toBeInstanceOf(TimeoutError)
  })
  it('surfaces CRIU capture errors while waiting for sandbox pause', async () => {
    response({status: 'running', pauseError: 'Disconnect active clients'})
    await expect(new Sandbox({sandboxId: 'sb-1', ...config}).waitForStatus('paused')).rejects.toThrow('Disconnect active clients')
  })
  it('waits for a resumed sandbox and bounds a pending operation', async () => {
    response({status: 'running'})
    expect(await new Sandbox({sandboxId: 'sb-1', ...config}).waitForStatus('running')).toMatchObject({status: 'running'})
    response({status: 'resuming'})
    await expect(new Sandbox({sandboxId: 'sb-1', ...config}).waitForStatus('running', {waitTimeoutMs: 0})).rejects.toBeInstanceOf(TimeoutError)
  })
})
