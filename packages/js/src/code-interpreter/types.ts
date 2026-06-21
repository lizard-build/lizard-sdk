/** A single output item produced during code execution. */
export type OutputItem =
  | { type: 'stdout'; data: string; ts: number }
  | { type: 'stderr'; data: string; ts: number }
  | { type: 'result'; mime: string; data: string }
  | { type: 'error'; name: string; message: string; traceback: string }

/** Error thrown when executed code raises an exception. */
export class ExecutionError extends Error {
  readonly name: string
  readonly traceback: string

  constructor(name: string, message: string, traceback: string) {
    super(message)
    this.name = name
    this.traceback = traceback
  }
}

/** Full result of a runCode() call. */
export class Execution {
  /** All stdout text, concatenated. */
  stdout = ''
  /** All stderr text, concatenated. */
  stderr = ''
  /** Rich output items (images, JSON, HTML, plain values). */
  results: OutputItem[] = []
  /** Execution error if the code threw an exception. */
  error?: ExecutionError
  /** Monotonically increasing counter for this context. */
  executionCount = 0

  get success(): boolean {
    return !this.error
  }

  get text(): string {
    return this.stdout
  }
}

/** An isolated stateful execution context. */
export type CodeContext = {
  id: string
  language: string
  cwd: string
}

export type RunCodeLanguage =
  | 'python'
  | 'javascript'
  | 'bash'
  | (string & Record<never, never>)

export interface RunCodeOpts {
  /** Language to run in. Defaults to python. */
  language?: RunCodeLanguage
  /** Use a specific context instead of the per-language default. */
  context?: CodeContext
  /** Extra environment variables available to the code. */
  envs?: Record<string, string>
  /** Max time to wait for the code to finish, in ms. Default: 60_000. */
  timeoutMs?: number
  onStdout?: (data: string) => void
  onStderr?: (data: string) => void
  onResult?: (item: OutputItem) => void
  onError?: (err: ExecutionError) => void
}

export interface CreateContextOpts {
  language?: RunCodeLanguage
  cwd?: string
}
