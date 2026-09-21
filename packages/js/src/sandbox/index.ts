import { ConnectionConfig, ConnectionOpts, DEFAULT_SANDBOX_TIMEOUT_MS } from '../config'
import { Process } from './process'
import { Fs } from './fs'
import { SandboxClient, SandboxInfo, SandboxOpts } from './client'

export { SandboxOpts, SandboxInfo }

/**
 * A Lizard sandbox — an isolated Linux environment that starts in under a second.
 *
 * Each sandbox is a full Linux environment with its own filesystem, network, and
 * process namespace, restored from a pre-warmed template snapshot.
 *
 * Sandboxes are **ephemeral**: killing one, or letting it hit its timeout, discards
 * everything written inside it. State that has to outlive a sandbox belongs on a
 * {@link Volume}, which is a separate disk you mount at `/data` and re-attach to a
 * later sandbox.
 *
 * @example Basic usage:
 * ```ts
 * import { Sandbox } from '@lizard-build/sdk'
 *
 * const sandbox = await Sandbox.create('base', { project: 'my-project' })
 * await sandbox.fs.write('/app/index.js', 'console.log("hello world")')
 * const result = await sandbox.process.exec('node /app/index.js')
 * console.log(result.stdout) // "hello world"
 * await sandbox.kill()
 * ```
 *
 * @example Carry work across sandboxes with a volume:
 * ```ts
 * const vol = await Volume.getOrCreate(projectId, 'agent-scratch', { sizeGb: 10 })
 *
 * const first = await Sandbox.create('codex', { projectId, volumeName: 'agent-scratch' })
 * await first.process.exec('echo "notes" > /data/notes.txt')
 * await first.kill()
 *
 * // A different sandbox, the same disk. No region to thread through: the sandbox
 * // is placed wherever the volume already lives.
 * const second = await Sandbox.create('codex', { projectId, volumeName: 'agent-scratch' })
 * console.log(await second.fs.read('/data/notes.txt')) // "notes"
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
   * const sandbox = await Sandbox.create({ project: 'my-project' })
   * ```
   */
  static async create(opts?: SandboxOpts): Promise<Sandbox>

  /**
   * Create a new Lizard sandbox from the specified template.
   *
   * Available templates: `base` (Debian + Node.js 26) and `code-interpreter-v1`
   * (Python 3.14 + Node.js 26). Custom templates can be built and pushed via
   * `lizard push`.
   *
   * @param template Name of the sandbox template to boot from.
   *
   * @example
   * ```ts
   * const sandbox = await Sandbox.create('base', { project: 'my-project' })
   * const sandbox = await Sandbox.create('code-interpreter-v1', { project: 'my-project', timeoutMs: 10 * 60 * 1000 })
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
   * Verifies the sandbox exists and is reachable, then returns a handle to it.
   * Throws `NotFoundError` if it has been killed or has expired.
   *
   * This used to call `resume` first, on the assumption that a sandbox you are
   * reconnecting to might be paused. Sandboxes are pods now and pause/resume is a
   * `501` on every one of them, so that call turned every `connect()` into an
   * error against a perfectly healthy sandbox. Connecting does not need to change
   * a sandbox's state, so it no longer tries to.
   *
   * @example
   * ```ts
   * const sandbox = await Sandbox.connect('sandbox_abc123')
   * ```
   */
  static async connect(sandboxId: string, opts?: ConnectionOpts): Promise<Sandbox> {
    await SandboxClient.getSandboxInfo(sandboxId, opts)
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
   * Pause the sandbox by freezing it in place.
   *
   * @deprecated Not implemented for the current runtime — always throws
   * `LizardError` with HTTP 501. Sandboxes run as pods, and the equivalent is a CRIU
   * checkpoint of the pod, which is not built. To park work across a gap, put it on a
   * {@link Volume} and create a fresh sandbox on that volume later; the volume is the
   * part that is meant to outlive a sandbox.
   */
  async pause(opts?: ConnectionOpts): Promise<boolean> {
    return SandboxClient.pauseSandbox(this.sandboxId, this.resolveOpts(opts))
  }

  /**
   * Resume a paused sandbox.
   *
   * @deprecated Not implemented for the current runtime — always throws
   * `LizardError` with HTTP 501. See {@link pause}. `Sandbox.connect()` no longer
   * calls this, so reconnecting to a running sandbox works without it.
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
