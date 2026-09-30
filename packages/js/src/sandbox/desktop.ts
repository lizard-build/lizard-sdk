import { ConnectionConfig } from '../config'
import { LizardError } from '../errors'
import { PlatformClient } from '../platform/client'
import { Process, ProcessResult } from './process'
import { Fs } from './fs'

/**
 * State of a sandbox's desktop, and the URLs that stream it.
 *
 * **Both URLs are credentials.** The port is published on a public hostname, and each
 * URL carries the stream token and a VNC password. Anyone holding `url` can see and
 * control the desktop; anyone holding `viewOnlyUrl` can watch it. Do not log them or
 * put them anywhere you would not put an API key.
 */
export interface DesktopInfo {
  running: boolean
  /** Screen width in pixels, or `null` when the desktop has never been started. */
  width: number | null
  height: number | null
  /** noVNC page with full control (mouse and keyboard). Treat like a credential. */
  url: string
  /** noVNC page that can only watch; enforced by the VNC server, not the page. */
  viewOnlyUrl: string
}

export interface DesktopStartOpts {
  /** Screen width, 640–3840. Pass together with `height`; default 1280x800. */
  width?: number
  /** Screen height, 480–2160. */
  height?: number
}

export type MouseButton = 'left' | 'right' | 'middle'
export type ScrollDirection = 'up' | 'down' | 'left' | 'right'

export interface ClickOpts {
  /** Default `'left'`. */
  button?: MouseButton
  /** Double-click instead of a single click. */
  double?: boolean
}

const BUTTONS: Record<MouseButton, string> = { left: '1', middle: '2', right: '3' }
const SCROLL_BUTTONS: Record<ScrollDirection, string> = { up: '4', down: '5', left: '6', right: '7' }
/** Where `lizard-desktop screenshot --path` writes its file (mktemp suffix). */
const SCREENSHOT_PATH = /^\/tmp\/lizard-screenshot-[A-Za-z0-9_-]+\.png$/
/** Milliseconds between typed characters; xdotool's own default (12) is what it is tuned for. */
const TYPE_DELAY_MS = 12

/**
 * A graphical desktop in the sandbox, for computer-use agents and for people to watch.
 *
 * Only the `desktop` template has one (Xvfb + XFCE + Chromium on `DISPLAY=:1`); on
 * any other template the calls fail with `code === 'DESKTOP_NOT_SUPPORTED'`.
 *
 * Input and screenshots run inside the sandbox with `xdotool` and `scrot`. Every
 * argument goes to the sandbox as an argv array and is never parsed by a shell, so
 * text typed on behalf of a model or a user cannot run commands.
 *
 * Access via `sandbox.desktop`.
 *
 * @example
 * ```ts
 * const sandbox = await Sandbox.create('desktop', { project: 'my-project' })
 * const { url } = await sandbox.desktop.start()   // open in a browser to watch/drive
 * await sandbox.desktop.openUrl('https://example.com')
 * await sandbox.desktop.click(640, 400)
 * await sandbox.desktop.type('hello')
 * await sandbox.desktop.press('Return')
 * const png = await sandbox.desktop.screenshot()
 * ```
 */
export class Desktop {
  constructor(
    private readonly sandboxId: string,
    private readonly config: ConnectionConfig,
    private readonly process: Process,
    private readonly fs: Fs,
  ) {}

  private get client(): PlatformClient {
    return new PlatformClient(this.config)
  }

  private get path(): string {
    return `/api/sandboxes/${encodeURIComponent(this.sandboxId)}/desktop`
  }

  /**
   * Start the desktop, publish its stream and return the URLs. Idempotent: calling
   * it on a running desktop returns the same URLs (the size of a running desktop is
   * not changed).
   */
  start(opts: DesktopStartOpts = {}): Promise<DesktopInfo> {
    const body: DesktopStartOpts = {}
    if (opts.width !== undefined) body.width = opts.width
    if (opts.height !== undefined) body.height = opts.height
    return this.client.post<DesktopInfo>(this.path, body)
  }

  /** The desktop's state and URLs, without starting it. */
  info(): Promise<DesktopInfo> {
    return this.client.get<DesktopInfo>(this.path)
  }

  /** Stop the desktop and unpublish its stream. Its URLs stay the same for the next start. */
  async stop(): Promise<void> {
    await this.client.delete<unknown>(this.path)
  }

  /**
   * A PNG of the whole screen. The desktop must be running.
   *
   * @example
   * ```ts
   * import { writeFileSync } from 'node:fs'
   * writeFileSync('screen.png', await sandbox.desktop.screenshot())
   * ```
   */
  async screenshot(): Promise<Uint8Array> {
    // The PNG goes through a file, not stdout: exec output is streamed in 64 KiB
    // lines and capped at 512 KiB, and a real page is a ~250 KB PNG.
    const r = await this.run(['lizard-desktop', 'screenshot', '--path'])
    const path = r.stdout.split('\n').map(l => l.trim()).filter(Boolean).pop() ?? ''
    if (!SCREENSHOT_PATH.test(path)) {
      throw new LizardError(`Screenshot returned an unexpected path: ${path.slice(0, 200)}`)
    }
    try {
      return await this.fs.readBytes(path)
    } finally {
      await this.fs.remove(path).catch(() => {})
    }
  }

  /** Click at (x, y). */
  async click(x: number, y: number, opts: ClickOpts = {}): Promise<void> {
    const button = BUTTONS[opts.button ?? 'left']
    if (!button) throw new LizardError(`Unknown mouse button: ${String(opts.button)}`)
    const repeat = opts.double ? ['--repeat', '2', '--delay', '100'] : []
    await this.run(['xdotool', 'mousemove', coord(x), coord(y), 'click', ...repeat, button])
  }

  /** Move the pointer to (x, y) without clicking. */
  async moveMouse(x: number, y: number): Promise<void> {
    await this.run(['xdotool', 'mousemove', coord(x), coord(y)])
  }

  /** Press the left button at (fromX, fromY), move to (toX, toY) and release. */
  async drag(fromX: number, fromY: number, toX: number, toY: number): Promise<void> {
    await this.run([
      'xdotool',
      'mousemove', coord(fromX), coord(fromY), 'mousedown', '1', 'sleep', '0.1',
      'mousemove', coord(toX), coord(toY), 'sleep', '0.1', 'mouseup', '1',
    ])
  }

  /**
   * Type text into the focused window, as keystrokes. The text is passed as a
   * single argument after `--`, never through a shell.
   */
  async type(text: string): Promise<void> {
    if (!text) return
    // ~12ms a character plus xdotool's own overhead; never below the default 60s.
    const timeoutMs = Math.min(600_000, Math.max(60_000, text.length * TYPE_DELAY_MS * 3))
    await this.run(['xdotool', 'type', '--delay', String(TYPE_DELAY_MS), '--', text], timeoutMs)
  }

  /**
   * Press a key or a chord, in xdotool keysym syntax: `'Return'`, `'ctrl+l'`,
   * `'alt+Tab'`. An array presses them one after another.
   */
  async press(keys: string | string[]): Promise<void> {
    const list = Array.isArray(keys) ? keys : [keys]
    if (list.length === 0 || list.some(k => typeof k !== 'string' || !k)) {
      throw new LizardError('press() needs at least one non-empty key')
    }
    await this.run(['xdotool', 'key', '--', ...list])
  }

  /** Scroll with the mouse wheel at the pointer's current position. `amount` is wheel clicks. */
  async scroll(direction: ScrollDirection, amount = 3): Promise<void> {
    const button = SCROLL_BUTTONS[direction]
    if (!button) throw new LizardError(`Unknown scroll direction: ${String(direction)}`)
    if (!Number.isInteger(amount) || amount < 1) throw new LizardError('scroll amount must be a positive integer')
    await this.run(['xdotool', 'click', '--repeat', String(amount), '--delay', '30', button])
  }

  /** Where the pointer is now. */
  async cursorPosition(): Promise<{ x: number; y: number }> {
    const r = await this.run(['xdotool', 'getmouselocation', '--shell'])
    const x = /^X=(\d+)$/m.exec(r.stdout)
    const y = /^Y=(\d+)$/m.exec(r.stdout)
    if (!x || !y) throw new LizardError(`Unexpected xdotool output: ${r.stdout.trim()}`)
    return { x: Number(x[1]), y: Number(y[1]) }
  }

  /**
   * Open a URL in a new Chromium window on the desktop. Returns once Chromium has
   * been launched, not when the page has loaded — take a screenshot to see it.
   */
  async openUrl(url: string): Promise<void> {
    // The URL is "$1" of the script, never part of the script text.
    await this.run([
      'sh', '-c', 'setsid chromium --new-window "$1" >/dev/null 2>&1 < /dev/null &', 'sh', url,
    ])
  }

  private async run(argv: string[], timeoutMs?: number): Promise<ProcessResult> {
    const r = await this.process.exec(argv, timeoutMs ? { timeoutMs } : undefined)
    if (r.exitCode !== 0) {
      const err = new LizardError(`${argv[0]} ${argv[1] ?? ''} failed (exit ${r.exitCode}): ${(r.stderr || r.stdout).trim()}`)
      if (r.exitCode === 127) err.code = 'DESKTOP_NOT_SUPPORTED'
      throw err
    }
    return r
  }
}

function coord(n: number): string {
  if (!Number.isFinite(n) || n < 0) throw new LizardError(`Invalid screen coordinate: ${n}`)
  return String(Math.round(n))
}
