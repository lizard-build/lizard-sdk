import { ConnectionConfig, ConnectionOpts, DEFAULT_SANDBOX_TIMEOUT_MS } from '../config'
import { Process } from './process'
import { Fs } from './fs'
import { SandboxClient, SandboxInfo, SandboxOpts } from './client'

export { SandboxOpts, SandboxInfo }

/**
 * A Lizard sandbox — an isolated Firecracker microVM that boots in milliseconds.
 *
 * Each sandbox is a full Linux environment with its own filesystem, network,
 * and process namespace. Sandboxes are spun up from templates and can be
 * paused to a snapshot, then resumed instantly — perfect for stateful AI
 * agent sessions or ephemeral code execution.
 *
 * @example Basic usage:
 * ```ts
 * import { Sandbox } from 'lizard'
 *
 * const sandbox = await Sandbox.create('base', { projectId: 'proj_abc123' })
 * await sandbox.fs.write('/app/index.js', 'console.log("hello world")')
 * const result = await sandbox.process.exec('node /app/index.js')
 * console.log(result.stdout) // "hello world"
 * await sandbox.kill()
 * ```
 *
 * @example Pause and resume a long-running session:
 * ```ts
 * const sandbox = await Sandbox.create('code-interpreter-v1', { projectId: 'proj_abc123' })
 * await sandbox.process.exec('pip install numpy')
 * const id = sandbox.sandboxId
 * await sandbox.pause()
 *
 * // Later — resume exactly where it left off:
 * const resumed = await Sandbox.connect(id)
 * await resumed.process.exec('python -c "import numpy; print(numpy.__version__)"')
 * ```
 */
export class Sandbox extends SandboxClient {
  protected static readonly defaultTemplate: string = 'base'
  protected static readonly defaultTimeoutMs = DEFAULT_SANDBOX_TIMEOUT_MS

  /**
   * Unique identifier of this sandbox microVM.
   */
  readonly sandboxId: string

  /**
   * Read and write files inside the microVM filesystem.
   *
   * @example
   * ```ts
   * await sandbox.fs.write('/app/main.py', 'print("hello")')
   * const src = await sandbox.fs.read('/app/main.py')
   * ```
   */
  readonly fs: Fs

  /**
   * Execute processes inside the microVM.
   *
   * @example
   * ```ts
   * const { stdout } = await sandbox.process.exec('python main.py')
   * ```
   */
  readonly process: Process

  protected readonly connectionConfig: ConnectionConfig

  constructor(opts: { sandboxId: string } & ConnectionOpts) {
    super()
    this.sandboxId = opts.sandboxId
    this.connectionConfig = new ConnectionConfig(opts)
    this.fs = new Fs(this.sandboxId, this.connectionConfig)
    this.process = new Process(this.sandboxId, this.connectionConfig)
  }

  /**
   * Create a new Lizard sandbox from the default `base` template.
   *
   * @example
   * ```ts
   * const sandbox = await Sandbox.create({ projectId: 'proj_abc123' })
   * ```
   */
  static async create(opts?: SandboxOpts): Promise<Sandbox>

  /**
   * Create a new Lizard sandbox from the specified template.
   *
   * Available templates: `base` (Debian + Node.js 20) and `code-interpreter-v1`
   * (Python 3.11 + Node.js 20). Custom templates can be built and pushed via
   * `lizard push`.
   *
   * @param template Name of the sandbox template to boot from.
   *
   * @example
   * ```ts
   * const sandbox = await Sandbox.create('base', { projectId: 'proj_abc123' })
   * const sandbox = await Sandbox.create('code-interpreter-v1', { projectId: 'proj_abc123', timeoutMs: 10 * 60 * 1000 })
   * ```
   */
  static async create(template: string, opts?: SandboxOpts): Promise<Sandbox>

  static async create(
    templateOrOpts?: string | SandboxOpts,
    opts?: SandboxOpts
  ): Promise<Sandbox> {
    const template = typeof templateOrOpts === 'string'
      ? templateOrOpts
      : (templateOrOpts?.template ?? this.defaultTemplate)

    const sandboxOpts = typeof templateOrOpts === 'string' ? opts : templateOrOpts
    const timeoutMs = sandboxOpts?.timeoutMs ?? this.defaultTimeoutMs

    const { sandboxId } = await SandboxClient.createSandbox(template, timeoutMs, sandboxOpts)
    return new this({ sandboxId, ...sandboxOpts })
  }

  /**
   * Connect to an existing sandbox by its ID.
   *
   * If the sandbox is currently paused, it will be automatically resumed
   * from its last snapshot before this call returns.
   *
   * @example
   * ```ts
   * const sandbox = await Sandbox.connect('sandbox_abc123')
   * ```
   */
  static async connect(sandboxId: string, opts?: ConnectionOpts): Promise<Sandbox> {
    await SandboxClient.resumeSandbox(sandboxId, opts)
    return new this({ sandboxId, ...opts })
  }

  /**
   * List all running sandboxes for the authenticated account.
   *
   * @example
   * ```ts
   * const sandboxes = await Sandbox.list()
   * ```
   */
  static async list(opts?: ConnectionOpts): Promise<SandboxInfo[]> {
    return SandboxClient.listSandboxes(opts)
  }

  /**
   * Kill the sandbox and release its resources immediately.
   *
   * @returns `true` if the microVM was terminated, `false` if it was already gone.
   */
  async kill(opts?: ConnectionOpts): Promise<boolean> {
    return SandboxClient.killSandbox(this.sandboxId, this.resolveOpts(opts))
  }

  /**
   * Snapshot and pause the sandbox microVM.
   *
   * The sandbox state — memory, filesystem, and running processes — is saved
   * to a snapshot. Resume with `sandbox.resume()` or `Sandbox.connect(id)`.
   *
   * @returns `true` if paused successfully.
   */
  async pause(opts?: ConnectionOpts): Promise<boolean> {
    return SandboxClient.pauseSandbox(this.sandboxId, this.resolveOpts(opts))
  }

  /**
   * Resume a paused sandbox from its last snapshot.
   *
   * @returns `true` if resumed successfully.
   */
  async resume(opts?: ConnectionOpts): Promise<boolean> {
    return SandboxClient.resumeSandbox(this.sandboxId, this.resolveOpts(opts))
  }

  /**
   * Get metadata and status information about this sandbox.
   */
  async getInfo(opts?: ConnectionOpts): Promise<SandboxInfo> {
    return SandboxClient.getSandboxInfo(this.sandboxId, this.resolveOpts(opts))
  }

  /**
   * Extend or reduce the sandbox timeout.
   *
   * @param timeoutMs New timeout in milliseconds measured from now.
   */
  async setTimeout(timeoutMs: number, opts?: ConnectionOpts): Promise<void> {
    return SandboxClient.setTimeoutSandbox(this.sandboxId, timeoutMs, this.resolveOpts(opts))
  }

  /**
   * Get the public HTTPS URL for a port exposed inside the sandbox.
   *
   * Useful for accessing HTTP servers started inside the microVM from your
   * agent or tests without additional tunneling.
   *
   * @example
   * ```ts
   * await sandbox.process.exec('npx -y serve -p 3000 &')
   * const url = sandbox.getHost(3000)
   * // https://{sandboxId}-3000.sandbox.{region}.onlizard.com
   * ```
   */
  async getHost(port: number, opts?: ConnectionOpts): Promise<string> {
    const { hostname } = await SandboxClient.exposeSandboxPort(this.sandboxId, port, this.resolveOpts(opts))
    return hostname
  }

  private resolveOpts(opts?: ConnectionOpts): ConnectionOpts {
    return { ...this.connectionConfig, ...opts }
  }
}
