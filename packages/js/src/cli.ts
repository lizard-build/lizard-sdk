import { spawn } from 'node:child_process'
import type { ConnectionOpts } from './config'

export interface CLIResult { code: number; stdout: string; stderr: string; events: unknown[] }
export interface CLIOptions extends ConnectionOpts { executable?: string; cwd?: string; timeoutMs?: number }

/** Optional adapter for local CLI workflows. Requires the Lizard CLI on PATH.
 * Arguments are passed directly, without a shell. It does not add --yes, retry
 * payments. Authentication follows the CLI configuration.
 */
export class LizardCLI {
  constructor(private readonly opts: CLIOptions = {}) {}
  run(args: readonly string[], opts: { stdin?: string; signal?: AbortSignal } = {}): Promise<CLIResult> {
    return new Promise((resolve, reject) => {
      const env = { ...process.env }
      if (this.opts.apiKey) { env.LIZARD_API_KEY = this.opts.apiKey; env.LIZARD_TOKEN = this.opts.apiKey }
      if (this.opts.apiUrl) env.LIZARD_API_URL = this.opts.apiUrl
      const child = spawn(this.opts.executable ?? 'lizard', ['--json', ...args], {
        cwd: this.opts.cwd, env, shell: false, stdio: 'pipe', signal: opts.signal,
        timeout: this.opts.timeoutMs ?? 600_000,
      })
      child.stdout.setEncoding('utf8')
      child.stderr.setEncoding('utf8')
      let stdout = '', stderr = '', bytes = 0
      const collect = (stream: 'stdout' | 'stderr', data: string) => {
        bytes += Buffer.byteLength(data)
        if (bytes > 16 * 1024 * 1024) { child.kill(); reject(new Error('CLI output exceeds 16 MiB')); return }
        if (stream === 'stdout') stdout += data; else stderr += data
      }
      child.stdout.on('data', data => collect('stdout', data))
      child.stderr.on('data', data => collect('stderr', data))
      child.on('error', reject)
      child.on('close', (code, signal) => {
        if (signal) { reject(new Error(`CLI ended with signal ${signal}`)); return }
        let events: unknown[] = []
        try { events = [JSON.parse(stdout)] } catch {
          events = stdout.split('\n').filter(Boolean).flatMap(line => { try { return [JSON.parse(line)] } catch { return [] } })
        }
        resolve({ code: code ?? 1, stdout, stderr, events })
      })
      child.stdin.on('error', error => { if ((error as NodeJS.ErrnoException).code !== 'EPIPE') reject(error) })
      child.stdin.end(opts.stdin)
    })
  }
}
