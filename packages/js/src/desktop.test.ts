import { afterEach, describe, expect, it, vi } from 'vitest'
import { Sandbox, LizardError } from './index'

const opts = { apiKey: 'liz_test', apiUrl: 'https://test.invalid' }
afterEach(() => { vi.unstubAllGlobals() })

/** Stub fetch; answer every request with `body` (and `status`), recording what was sent. */
function stub(body: unknown = { stdout: '', stderr: '', exitCode: 0 }, status = 200) {
  const calls: Array<{ url: string; method: string; body: any }> = []
  vi.stubGlobal('fetch', vi.fn(async (url: string, init: RequestInit = {}) => {
    calls.push({ url: String(url), method: init.method ?? 'GET', body: init.body ? JSON.parse(String(init.body)) : undefined })
    return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
  }))
  return calls
}
const sandbox = () => new Sandbox({ sandboxId: 'sb1', ...opts })
const INFO = { running: true, width: 1280, height: 800, url: 'https://x/vnc.html?password=p', viewOnlyUrl: 'https://x/vnc.html?view_only=true' }

describe('sandbox.desktop REST', () => {
  it('start posts the size and returns the URLs', async () => {
    const calls = stub(INFO)
    expect(await sandbox().desktop.start({ width: 1920, height: 1080 })).toEqual(INFO)
    expect(calls).toEqual([{ url: 'https://test.invalid/api/sandboxes/sb1/desktop', method: 'POST', body: { width: 1920, height: 1080 } }])
  })
  it('start without a size sends an empty body', async () => {
    const calls = stub(INFO)
    await sandbox().desktop.start()
    expect(calls[0].body).toEqual({})
  })
  it('info is a GET and stop is a DELETE', async () => {
    const calls = stub(INFO)
    await sandbox().desktop.info()
    await sandbox().desktop.stop()
    expect(calls.map(c => `${c.method} ${c.url}`)).toEqual([
      'GET https://test.invalid/api/sandboxes/sb1/desktop',
      'DELETE https://test.invalid/api/sandboxes/sb1/desktop',
    ])
  })
  it('surfaces DESKTOP_NOT_SUPPORTED as the error code', async () => {
    stub({ error: "The 'base' template has no desktop.", code: 'DESKTOP_NOT_SUPPORTED' }, 400)
    await expect(sandbox().desktop.start()).rejects.toMatchObject({ code: 'DESKTOP_NOT_SUPPORTED', status: 400 })
  })
})

describe('sandbox.desktop input', () => {
  const exec = (calls: Array<{ url: string; body: any }>) => {
    expect(calls).toHaveLength(1)
    expect(calls[0].url).toBe('https://test.invalid/api/sandboxes/sb1/exec')
    return calls[0].body.cmd
  }

  it('type sends the text as one argv element after --, never through a shell', async () => {
    const calls = stub()
    const text = `"; rm -rf / #$(id) \`id\` 'quote' && echo pwned`
    await sandbox().desktop.type(text)
    expect(exec(calls)).toEqual(['xdotool', 'type', '--delay', '12', '--', text])
  })
  it('type keeps a leading dash as text, not an option', async () => {
    const calls = stub()
    await sandbox().desktop.type('--help')
    expect(exec(calls)).toEqual(['xdotool', 'type', '--delay', '12', '--', '--help'])
  })
  it('click moves then clicks with the right button number', async () => {
    let calls = stub()
    await sandbox().desktop.click(10, 20)
    expect(exec(calls)).toEqual(['xdotool', 'mousemove', '10', '20', 'click', '1'])
    calls = stub()
    await sandbox().desktop.click(10.4, 20.6, { button: 'right', double: true })
    expect(exec(calls)).toEqual(['xdotool', 'mousemove', '10', '21', 'click', '--repeat', '2', '--delay', '100', '3'])
  })
  it('rejects bad coordinates before sending', async () => {
    const calls = stub()
    await expect(sandbox().desktop.click(NaN, 1)).rejects.toBeInstanceOf(LizardError)
    await expect(sandbox().desktop.moveMouse(-1, 1)).rejects.toBeInstanceOf(LizardError)
    expect(calls).toHaveLength(0)
  })
  it('press sends each key as its own argument', async () => {
    let calls = stub()
    await sandbox().desktop.press('ctrl+l')
    expect(exec(calls)).toEqual(['xdotool', 'key', '--', 'ctrl+l'])
    calls = stub()
    await sandbox().desktop.press(['ctrl+a', 'BackSpace; reboot'])
    expect(exec(calls)).toEqual(['xdotool', 'key', '--', 'ctrl+a', 'BackSpace; reboot'])
  })
  it('moveMouse, drag and scroll', async () => {
    let calls = stub()
    await sandbox().desktop.moveMouse(5, 6)
    expect(exec(calls)).toEqual(['xdotool', 'mousemove', '5', '6'])
    calls = stub()
    await sandbox().desktop.drag(1, 2, 3, 4)
    expect(exec(calls)).toEqual(['xdotool', 'mousemove', '1', '2', 'mousedown', '1', 'sleep', '0.1', 'mousemove', '3', '4', 'sleep', '0.1', 'mouseup', '1'])
    calls = stub()
    await sandbox().desktop.scroll('down')
    expect(exec(calls)).toEqual(['xdotool', 'click', '--repeat', '3', '--delay', '30', '5'])
    calls = stub()
    await sandbox().desktop.scroll('left', 1)
    expect(exec(calls)).toEqual(['xdotool', 'click', '--repeat', '1', '--delay', '30', '6'])
  })
  it('openUrl passes the URL as $1 of a fixed script', async () => {
    const calls = stub()
    const url = 'https://example.com/?q=$(id)&x=`id`'
    await sandbox().desktop.openUrl(url)
    const argv = exec(calls)
    expect(argv).toEqual(['sh', '-c', 'setsid chromium --new-window "$1" >/dev/null 2>&1 < /dev/null &', 'sh', url])
    expect(argv[2]).not.toContain(url)
  })
  it('cursorPosition parses xdotool --shell output', async () => {
    const calls = stub({ stdout: 'X=640\nY=400\nSCREEN=0\nWINDOW=123\n', stderr: '', exitCode: 0 })
    expect(await sandbox().desktop.cursorPosition()).toEqual({ x: 640, y: 400 })
    expect(exec(calls)).toEqual(['xdotool', 'getmouselocation', '--shell'])
  })
  it('screenshot runs lizard-desktop and decodes the base64 PNG', async () => {
    const png = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 255])
    const calls = stub({ stdout: Buffer.from(png).toString('base64') + '\n', stderr: '', exitCode: 0 })
    const shot = await sandbox().desktop.screenshot()
    expect(shot).toBeInstanceOf(Uint8Array)
    expect([...shot]).toEqual([...png])
    expect(exec(calls)).toEqual(['lizard-desktop', 'screenshot'])
  })
  it('screenshot refuses truncated output instead of returning a broken PNG', async () => {
    stub({ stdout: 'iVBORw0KGgo', stderr: '', exitCode: 0, truncated: true })
    await expect(sandbox().desktop.screenshot()).rejects.toThrow('exec output limit')
  })
  it('a failed command throws with its stderr', async () => {
    stub({ stdout: '', stderr: 'lizard-desktop: the desktop is not running', exitCode: 1 })
    await expect(sandbox().desktop.screenshot()).rejects.toThrow('the desktop is not running')
  })
  it('a missing tool is reported as DESKTOP_NOT_SUPPORTED', async () => {
    stub({ stdout: '', stderr: 'sh: xdotool: not found', exitCode: 127 })
    await expect(sandbox().desktop.click(1, 1)).rejects.toMatchObject({ code: 'DESKTOP_NOT_SUPPORTED' })
  })
})
