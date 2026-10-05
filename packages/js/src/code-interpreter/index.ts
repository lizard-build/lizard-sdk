import { Sandbox, SandboxOpts } from '../sandbox'
import { ConnectionOpts } from '../config'
import { LizardError } from '../errors'
import {
  Execution,
  ExecutionError,
  OutputItem,
  CodeContext,
  RunCodeOpts,
  CreateContextOpts,
} from './types'
import { RUNNER_SOURCE } from './runner'

export { Execution, ExecutionError, CodeContext, RunCodeOpts, CreateContextOpts }
export type { RunCodeLanguage } from './types'

/** Default execution timeout for {@link CodeSandbox.runCode}. */
const DEFAULT_RUN_TIMEOUT_MS = 60_000
/** Extra time the exec call gets on top of the code's own timeout (kernel start-up). */
const RUNNER_OVERHEAD_MS = 45_000
/** Encoded arguments above this go through a file instead of argv (128 KiB per-argument limit). */
const MAX_INLINE_ARGS = 100_000

type RunnerEvent = Record<string, unknown> & { type?: string }

/**
 * A sandbox for running code snippets, built on {@link Sandbox.process}.
 *
 * Boots the `interpreter` template by default. Python runs in a persistent
 * Jupyter kernel per context, so variables, imports and functions carry over
 * between calls, `execution.results` holds rich output (the value of the last
 * expression, matplotlib charts as `image/png`, HTML, ...) and errors carry
 * the exception name and traceback.
 *
 * Limits, honestly:
 * - `javascript` (node) and `bash` run each call as a fresh process: no state
 *   carries over and `results` stays empty. `node` must be installed in the
 *   template; the `interpreter` template does not ship it.
 * - On a template without Jupyter (e.g. `base`), Python also runs as a fresh
 *   process per call.
 * - `stdout`/`stderr` are delivered in the chunks the kernel or process
 *   produced them, not per character.
 *
 * Kernels live inside the sandbox's microVM, so pause/resume, snapshots and
 * forks keep their state.
 *
 * @example
 * ```ts
 * const sandbox = await CodeSandbox.create({ project: 'my-project' })
 * await sandbox.runCode('x = 21')
 * const run = await sandbox.runCode('x * 2')
 * console.log(run.results[0].data) // "42"
 * await sandbox.kill()
 * ```
 */
export class CodeSandbox extends Sandbox {
  protected static override readonly defaultTemplate: string = 'interpreter'

  /**
   * Execute code and wait for it to finish.
   *
   * Python keeps its state per context (the default context, per language,
   * when none is given). Code errors appear in `execution.error`; request
   * failures throw.
   *
   * @param code  Source code to run.
   * @param opts  Language, context, env vars, timeout, and streaming callbacks.
   *
   * @example
   * ```ts
   * const result = await sandbox.runCode(`
   *   import math
   *   print(math.sqrt(144))
   * `)
   * console.log(result.stdout) // "12.0\n"
   * ```
   */
  async runCode(code: string, opts?: RunCodeOpts): Promise<Execution> {
    if (opts?.context && opts?.language) {
      throw new Error('Provide context or language, not both')
    }
    const timeoutMs = opts?.timeoutMs ?? DEFAULT_RUN_TIMEOUT_MS
    const args: Record<string, unknown> = {
      action: 'run',
      code,
      envs: opts?.envs ?? {},
      timeout: timeoutMs / 1000,
    }
    if (opts?.context) args.context = opts.context.id
    else args.language = opts?.language ?? 'python'

    const execution = new Execution()
    await this.runner(args, timeoutMs, (item) => {
      if (item.type === 'stdout') {
        execution.stdout += item.data as string
        opts?.onStdout?.(item.data as string)
      } else if (item.type === 'stderr') {
        execution.stderr += item.data as string
        opts?.onStderr?.(item.data as string)
      } else if (item.type === 'result') {
        const out: OutputItem = { type: 'result', mime: item.mime as string, data: item.data as string }
        execution.results.push(out)
        opts?.onResult?.(out)
      } else if (item.type === 'error') {
        const err = new ExecutionError(item.name as string, item.message as string, item.traceback as string)
        execution.error = err
        opts?.onError?.(err)
      } else if (item.type === 'done') {
        execution.executionCount = (item.execution_count as number) ?? 0
      }
    })
    return execution
  }

  /**
   * Create a new isolated execution context.
   *
   * A Python context is its own kernel: its own variables, and `cwd` as its
   * working directory. Other languages get the working directory only.
   *
   * @example
   * ```ts
   * const ctx = await sandbox.createContext({ language: 'python' })
   * await sandbox.runCode('x = 10', { context: ctx })
   * await sandbox.runCode('print(x)', { context: ctx }) // prints 10
   * ```
   */
  async createContext(opts?: CreateContextOpts): Promise<CodeContext> {
    const id = `ctx-${randomId()}`
    let ctx: CodeContext | undefined
    await this.runner({ action: 'create', id, language: opts?.language ?? 'python', cwd: opts?.cwd ?? '/home/user' },
      DEFAULT_RUN_TIMEOUT_MS, (ev) => {
        if (ev.type === 'context') ctx = { id: ev.id as string, language: ev.language as string, cwd: ev.cwd as string }
      })
    if (!ctx) throw new LizardError('Failed to create context')
    return ctx
  }

  /** List the contexts created with {@link createContext} in this sandbox. */
  async listContexts(): Promise<CodeContext[]> {
    let out: CodeContext[] = []
    await this.runner({ action: 'list' }, DEFAULT_RUN_TIMEOUT_MS, (ev) => {
      if (ev.type === 'contexts') out = ev.data as CodeContext[]
    })
    return out
  }

  /** Delete an execution context, stopping its kernel. */
  async deleteContext(context: CodeContext | string): Promise<void> {
    const id = typeof context === 'string' ? context : context.id
    await this.runner({ action: 'delete', context: id }, DEFAULT_RUN_TIMEOUT_MS, () => {})
  }

  /** Restart a context, clearing all variables and state. */
  async restartContext(context: CodeContext | string): Promise<void> {
    const id = typeof context === 'string' ? context : context.id
    await this.runner({ action: 'restart', context: id }, DEFAULT_RUN_TIMEOUT_MS, () => {})
  }

  /** Run the in-sandbox runner with `args` and hand each of its events to `onEvent`. */
  private async runner(args: Record<string, unknown>, timeoutMs: number, onEvent: (ev: RunnerEvent) => void): Promise<void> {
    let encoded = toBase64(JSON.stringify(args))
    if (encoded.length > MAX_INLINE_ARGS && typeof args.code === 'string') {
      const codeFile = `/tmp/.lizard-code/in-${randomId()}`
      await this.fs.write(codeFile, args.code as string)
      const { code: _code, ...rest } = args
      encoded = toBase64(JSON.stringify({ ...rest, codeFile }))
    }

    let part = ''
    let fatal: string | undefined
    let sawEvent = false
    const stderr: string[] = []
    const result = await this.process.exec(['python3', '-c', RUNNER_SOURCE, encoded], {
      timeoutMs: timeoutMs + RUNNER_OVERHEAD_MS,
      onStdout: (line) => {
        let ev: RunnerEvent
        try {
          ev = JSON.parse(line)
          // An event too long for one output line arrives as pieces.
          if (ev.type === 'part') {
            part += ev.data as string
            if (!ev.end) return
            ev = JSON.parse(part)
            part = ''
          }
        } catch {
          part = ''
          return
        }
        sawEvent = true
        if (ev.type === 'fatal') fatal = ev.message as string
        else onEvent(ev)
      },
      onStderr: (line) => { stderr.push(line) },
    })
    if (fatal) throw new LizardError(fatal)
    if (result.exitCode !== 0 || !sawEvent) {
      const detail = stderr.slice(-20).join('\n').trim() || `exit code ${result.exitCode}`
      throw new LizardError(`Code runner failed (python3 is required in the sandbox): ${detail}`)
    }
  }

  static override async create(opts?: SandboxOpts): Promise<CodeSandbox>
  static override async create(template: string, opts?: SandboxOpts): Promise<CodeSandbox>
  static override async create(
    templateOrOpts?: string | SandboxOpts,
    opts?: SandboxOpts
  ): Promise<CodeSandbox> {
    return super.create(templateOrOpts as string, opts) as Promise<CodeSandbox>
  }

  static override async connect(sandboxId: string, opts?: ConnectionOpts): Promise<CodeSandbox> {
    return super.connect(sandboxId, opts) as Promise<CodeSandbox>
  }
}

function randomId(): string {
  const c = (globalThis as { crypto?: { randomUUID?: () => string } }).crypto
  return c?.randomUUID ? c.randomUUID().replace(/-/g, '').slice(0, 16) : Math.random().toString(16).slice(2, 18)
}

function toBase64(text: string): string {
  if (typeof Buffer !== 'undefined') return Buffer.from(text, 'utf8').toString('base64')
  const bytes = new TextEncoder().encode(text)
  let s = ''
  for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode(...bytes.subarray(i, i + 0x8000))
  return btoa(s)
}
