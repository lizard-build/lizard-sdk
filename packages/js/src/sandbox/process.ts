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
  onStdout?: (data: string) => void
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
    const res = await fetch(`${this.config.apiUrl}/api/sandboxes/${this.sandboxId}/exec`, {
      method: 'POST',
      headers: this.config.headers,
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
    return res.json() as Promise<ProcessResult>
  }
}
