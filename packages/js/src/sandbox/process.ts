import { ConnectionConfig } from '../config'
import { handleApiError } from '../errors'

/**
 * The result of a process execution inside a Lizard microVM.
 */
export interface ProcessResult {
  stdout: string
  stderr: string
  exitCode: number
}

export interface ProcessOpts {
  timeoutMs?: number
  envs?: Record<string, string>
  user?: string
  workdir?: string
  /** Called with each stdout line as it is produced, rather than at the end. */
  onStdout?: (data: string) => void
  /** Called with each stderr line as it is produced, rather than at the end. */
  onStderr?: (data: string) => void
}

/**
 * Runs processes inside a Lizard sandbox microVM.
 *
 * Access via `sandbox.process`.
 */
export class Process {
  constructor(
    private readonly sandboxId: string,
    private readonly config: ConnectionConfig
  ) {}

  /**
   * Execute a command inside the microVM and wait for it to complete.
   *
   * The command runs in a shell inside the Lizard sandbox and returns
   * stdout, stderr, and the exit code when it finishes.
   *
   * @param cmd Shell command to run inside the microVM.
   * @param opts Optional execution options — environment variables, working
   *   directory, user, and timeout.
   *
   * @example
   * ```ts
   * const result = await sandbox.process.exec('node index.js')
   * console.log(result.stdout)
   * ```
   *
   * @example Run with a custom working directory and env vars:
   * ```ts
   * const result = await sandbox.process.exec('npm test', {
   *   workdir: '/app',
   *   envs: { NODE_ENV: 'test' },
   * })
   * ```
   */
  async exec(cmd: string, opts?: ProcessOpts): Promise<ProcessResult> {
    // `onStdout`/`onStderr` have been in ProcessOpts since the beginning but were
    // never wired up — passing them did nothing and the caller waited for the whole
    // command regardless. The platform has always streamed the output; it just needs
    // to be asked for it with an SSE Accept header.
    const streaming = Boolean(opts?.onStdout || opts?.onStderr)

    const res = await fetch(`${this.config.apiUrl}/api/sandboxes/${this.sandboxId}/exec`, {
      method: 'POST',
      headers: streaming
        ? { ...this.config.headers, Accept: 'text/event-stream' }
        : this.config.headers,
      body: JSON.stringify({
        cmd,
        envs: opts?.envs,
        user: opts?.user,
        workdir: opts?.workdir,
        timeoutMs: opts?.timeoutMs,
      }),
      signal: AbortSignal.timeout(opts?.timeoutMs ?? 60_000),
    })

    if (!res.ok) await handleApiError(res)
    if (!streaming) return res.json() as Promise<ProcessResult>
    return this.consumeStream(res, opts!)
  }

  /**
   * Read an SSE exec stream, handing each line to the caller as it arrives while
   * still accumulating the full result. Events are `{stream, line}` for output and
   * `{exitCode}` at the end.
   */
  private async consumeStream(res: Response, opts: ProcessOpts): Promise<ProcessResult> {
    const reader = res.body?.getReader()
    if (!reader) return { stdout: '', stderr: '', exitCode: 0 }

    const decoder = new TextDecoder()
    let buf = ''
    let stdout = ''
    let stderr = ''
    let exitCode = 0

    const handle = (raw: string) => {
      if (!raw.startsWith('data:')) return
      let ev: { stream?: string; line?: string; exitCode?: number }
      try {
        ev = JSON.parse(raw.slice(5).trim())
      } catch {
        return // a partial or non-JSON keepalive frame
      }
      if (ev.line !== undefined) {
        if (ev.stream === 'stderr') {
          stderr += ev.line + '\n'
          opts.onStderr?.(ev.line)
        } else {
          stdout += ev.line + '\n'
          opts.onStdout?.(ev.line)
        }
      }
      if (ev.exitCode !== undefined) exitCode = ev.exitCode
    }

    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      // Keep the trailing fragment: a chunk boundary can land mid-line, and parsing
      // half an event would drop it silently.
      const lines = buf.split('\n')
      buf = lines.pop() ?? ''
      for (const l of lines) handle(l)
    }
    if (buf) handle(buf)

    return { stdout: stdout.trimEnd(), stderr: stderr.trimEnd(), exitCode }
  }
}
