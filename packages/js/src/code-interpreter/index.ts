import { Sandbox, SandboxOpts } from '../sandbox'
import { ConnectionOpts } from '../config'
import {
  Execution,
  ExecutionError,
  OutputItem,
  CodeContext,
  RunCodeOpts,
  CreateContextOpts,
} from './types'

export { Execution, ExecutionError, CodeContext, RunCodeOpts, CreateContextOpts }
export type { RunCodeLanguage } from './types'

const CODE_INTERPRETER_PORT = 8080

/**
 * A Lizard sandbox with built-in stateful code execution.
 *
 * Extends the base Sandbox with `runCode()` — executes code in a persistent
 * kernel so variables and imports survive between calls.
 *
 * Supports Python, JavaScript (Node.js), and Bash out of the box.
 *
 * @example
 * ```ts
 * import { CodeSandbox } from 'lizard/code-interpreter'
 *
 * const sandbox = await CodeSandbox.create({ projectId: 'proj_abc123' })
 *
 * await sandbox.runCode('x = 42')
 * const result = await sandbox.runCode('print(x * 2)')
 * console.log(result.stdout) // "84\n"
 *
 * await sandbox.kill()
 * ```
 *
 * @example Run JavaScript:
 * ```ts
 * const result = await sandbox.runCode('1 + 1', { language: 'javascript' })
 * console.log(result.results[0].data) // "2"
 * ```
 */
export class CodeSandbox extends Sandbox {
  protected static override readonly defaultTemplate = 'code-interpreter-v1'

  private get serverUrl(): Promise<string> {
    return this.getHost(CODE_INTERPRETER_PORT).then(h => `https://${h}`)
  }

  /**
   * Execute code in a persistent kernel.
   *
   * Variables, imports, and function definitions from previous calls are
   * available in subsequent calls within the same context.
   *
   * @param code  Source code to run.
   * @param opts  Language, context, env vars, timeout, and streaming callbacks.
   *
   * @returns Execution result with stdout, stderr, results, and any error.
   *
   * @throws {ExecutionError} if you pass neither language nor context and no
   *   default context exists — which cannot happen in normal usage.
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

    const body: Record<string, unknown> = { code, env_vars: opts?.envs ?? {} }
    if (opts?.context) body.context_id = opts.context.id
    else if (opts?.language) body.language = opts.language

    const controller = new AbortController()
    const timer = opts?.timeoutMs
      ? setTimeout(() => controller.abort(), opts.timeoutMs)
      : undefined

    try {
      const res = await fetch(`${await this.serverUrl}/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: controller.signal,
      })

      if (!res.ok) {
        throw new Error(`Code interpreter returned ${res.status}: ${await res.text()}`)
      }

      if (!res.body) throw new Error('Empty response body')

      const execution = new Execution()

      for await (const line of readLines(res.body)) {
        let item: Record<string, unknown>
        try {
          item = JSON.parse(line)
        } catch {
          continue
        }

        if (item.type === 'stdout') {
          execution.stdout += item.data as string
          opts?.onStdout?.(item.data as string)
        } else if (item.type === 'stderr') {
          execution.stderr += item.data as string
          opts?.onStderr?.(item.data as string)
        } else if (item.type === 'result') {
          const out = item as unknown as OutputItem
          execution.results.push(out)
          opts?.onResult?.(out)
        } else if (item.type === 'error') {
          const err = new ExecutionError(
            item.name as string,
            item.message as string,
            item.traceback as string
          )
          execution.error = err
          opts?.onError?.(err)
        } else if (item.type === 'done') {
          execution.executionCount = (item.execution_count as number) ?? 0
          break
        }
      }

      return execution
    } finally {
      clearTimeout(timer)
    }
  }

  /**
   * Create a new isolated execution context.
   *
   * Each context maintains its own variable namespace and process state.
   * Useful for running multiple independent sessions in the same sandbox.
   *
   * @example
   * ```ts
   * const ctx = await sandbox.createContext({ language: 'python' })
   * await sandbox.runCode('x = 10', { context: ctx })
   * await sandbox.runCode('print(x)', { context: ctx }) // prints 10
   * ```
   */
  async createContext(opts?: CreateContextOpts): Promise<CodeContext> {
    const res = await fetch(`${await this.serverUrl}/contexts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        language: opts?.language ?? 'python',
        cwd: opts?.cwd ?? '/home/user',
      }),
    })
    if (!res.ok) throw new Error(`Failed to create context: ${await res.text()}`)
    return res.json()
  }

  /**
   * List all active execution contexts in this sandbox.
   */
  async listContexts(): Promise<CodeContext[]> {
    const res = await fetch(`${await this.serverUrl}/contexts`)
    if (!res.ok) throw new Error(`Failed to list contexts: ${await res.text()}`)
    return res.json()
  }

  /**
   * Delete an execution context and free its resources.
   */
  async deleteContext(context: CodeContext | string): Promise<void> {
    const id = typeof context === 'string' ? context : context.id
    const res = await fetch(`${await this.serverUrl}/contexts/${id}`, { method: 'DELETE' })
    if (!res.ok) throw new Error(`Failed to delete context: ${await res.text()}`)
  }

  /**
   * Restart a context, clearing all variables and state.
   */
  async restartContext(context: CodeContext | string): Promise<void> {
    const id = typeof context === 'string' ? context : context.id
    const res = await fetch(`${await this.serverUrl}/contexts/${id}/restart`, { method: 'POST' })
    if (!res.ok) throw new Error(`Failed to restart context: ${await res.text()}`)
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

async function* readLines(body: ReadableStream<Uint8Array>): AsyncIterable<string> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buf = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop() ?? ''
      for (const line of lines) {
        if (line.trim()) yield line
      }
    }
    if (buf.trim()) yield buf
  } finally {
    reader.releaseLock()
  }
}
