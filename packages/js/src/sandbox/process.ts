import { ConnectionConfig } from '../config'
import { handleApiError } from '../errors'

/** A process this sandbox is currently running (one started through `exec`). */
export interface ProcessInfo {
  pid: number
  /** The argv: `['/bin/sh', '-c', 'npm test']` for a shell command. */
  cmd: string[]
  /** `cmd` joined with spaces, for display. */
  command?: string
  /** Working directory the process was started in, when known. */
  cwd?: string | null
  /** The process's tag, when it was started with one. */
  tag?: string | null
  /** When the process started, unix milliseconds. Not reported by every sandbox. */
  startedAt?: number
}

/** Signals accepted by {@link Process.kill}. */
export type ProcessSignal =
  | 'SIGTERM' | 'SIGKILL' | 'SIGINT' | 'SIGHUP' | 'SIGQUIT' | 'SIGUSR1' | 'SIGUSR2'

/**
 * The result of a process execution inside a Lizard sandbox.
 */
export interface ProcessResult {
  stdout: string
  stderr: string
  exitCode: number
  /** Set when the platform cut the output off at its per-stream limit (512 KiB). */
  truncated?: boolean
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
  /**
   * Called once with the process's pid, before any output. Gives a streaming
   * `exec` something to pass to {@link Process.kill}.
   */
  onPid?: (pid: number) => void
}

/**
 * Runs processes inside a Lizard sandbox.
 *
 * Access via `sandbox.process`.
 */
export class Process {
  constructor(
    private readonly sandboxId: string,
    private readonly config: ConnectionConfig
  ) {}

  /**
   * Execute a command inside the sandbox and wait for it to complete.
   *
   * The command runs in a shell inside the Lizard sandbox and returns
   * stdout, stderr, and the exit code when it finishes.
   *
   * @param cmd Shell command to run inside the sandbox, or an argv array that is
   *   executed directly with no shell — nothing in it is interpreted, so it is the
   *   safe way to pass untrusted text as an argument.
   * @param opts Optional execution options — environment variables, working
   *   directory, user, and timeout.
   *
   * @example
   * ```ts
   * const result = await sandbox.process.exec('node index.js')
   * console.log(result.stdout)
   * ```
   *
   * @example Pass untrusted text as an argument, not through a shell:
   * ```ts
   * await sandbox.process.exec(['grep', '-rn', '--', userQuery, '/workspace'])
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
  async exec(cmd: string | string[], opts?: ProcessOpts): Promise<ProcessResult> {
    // `onStdout`/`onStderr` have been in ProcessOpts since the beginning but were
    // never wired up — passing them did nothing and the caller waited for the whole
    // command regardless. The platform has always streamed the output; it just needs
    // to be asked for it with an SSE Accept header.
    const streaming = Boolean(opts?.onStdout || opts?.onStderr || opts?.onPid)

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
        // The pid event is opt-in: older CLIs print any unknown data line as output.
        pidEvent: opts?.onPid ? true : undefined,
      }),
      signal: AbortSignal.timeout(opts?.timeoutMs ?? 60_000),
    })

    if (!res.ok) await handleApiError(res)
    if (!streaming) return res.json() as Promise<ProcessResult>
    return this.consumeStream(res, opts!)
  }

  /**
   * List the processes this sandbox is currently running.
   *
   * Only processes started through `exec` — not every process in the guest.
   * Those are the ones you can act on; the rest are the image's own business.
   *
   * @example
   * ```ts
   * for (const p of await sandbox.process.list()) {
   *   console.log(p.pid, p.cmd.join(' '))
   * }
   * ```
   */
  async list(): Promise<ProcessInfo[]> {
    const res = await fetch(`${this.config.apiUrl}/api/sandboxes/${this.sandboxId}/processes`, {
      headers: this.config.headers,
    })
    if (!res.ok) await handleApiError(res)
    return res.json() as Promise<ProcessInfo[]>
  }

  /**
   * Signal a running process. Defaults to `SIGTERM`.
   *
   * The signal goes to the whole process tree, so a shell's children die with
   * it — killing `sh -c 'sleep 100'` otherwise leaves the sleep running.
   *
   * The pid comes from {@link list}, or from the `pid` event at the start of a
   * streaming `exec`.
   *
   * @example Stop a long build:
   * ```ts
   * const [build] = await sandbox.process.list()
   * await sandbox.process.kill(build.pid)
   * ```
   */
  async kill(pid: number, signal: ProcessSignal = 'SIGTERM'): Promise<void> {
    const res = await fetch(`${this.config.apiUrl}/api/sandboxes/${this.sandboxId}/processes/signal`, {
      method: 'POST',
      headers: this.config.headers,
      body: JSON.stringify({ pid, signal }),
    })
    if (!res.ok) await handleApiError(res)
  }

  /**
   * Read an SSE exec stream, handing each line to the caller as it arrives while
   * still accumulating the full result. Events are `{pid}` first (when asked for
   * with `pidEvent`), `{stream, line}` for output and `{exitCode}` at the end.
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
      let ev: { stream?: string; line?: string; exitCode?: number; pid?: number }
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
      if (ev.pid !== undefined) opts.onPid?.(ev.pid)
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
