import { PlatformClient, query } from '../platform/client'
import { ConnectionConfig, ConnectionOpts, DEFAULT_SANDBOX_TIMEOUT_MS } from '../config'
import { Process } from './process'
import { Fs } from './fs'
import { Desktop } from './desktop'
import { SandboxClient, SandboxInfo, SandboxOpts, ExposedPort } from './client'
import { TimeoutError, ConflictError } from '../errors'

export { SandboxOpts, SandboxInfo, ExposedPort }

export interface SandboxSnapshot {
  id: string
  name: string
  projectId: string
  workspaceId: string
  region: string
  sourceSandboxId: string
  status: 'building' | 'warming' | 'ready' | 'paused' | 'suspended' | 'failed'
  poolSize: number
  readyCount: number
  error: string | null
  cpus: number
  memoryMb: number
  /** Unix milliseconds. */
  createdAt: number
}
export interface SnapshotOpts {
  /** Warm copies to keep ready (container sandboxes only; ignored for Firecracker, whose snapshots restore from disk). */
  poolSize?: number
}

/**
 * One entry of {@link Sandbox.fork}'s result: the new sandbox, or why that copy
 * could not be made (e.g. the account's sandbox limit).
 */
export type ForkResult<S extends Sandbox = Sandbox> =
  | { sandbox: S; info: SandboxInfo; error?: undefined }
  | { sandbox?: undefined; info?: undefined; error: string }
export interface SnapshotWaitOpts extends ConnectionOpts { waitTimeoutMs?: number }


/**
 * A Linux sandbox: a Firecracker microVM with its own kernel.
 *
 * Run commands, read and write files, and expose HTTP ports in a sandbox. A
 * sandbox boots in well under a second; {@link pause} and {@link resume} keep its
 * memory and running processes, {@link snapshot} saves it in about 2 s and
 * {@link restore} starts a copy in about 0.4 s, and {@link fork} clones a running
 * sandbox, processes and all.
 *
 * Sandboxes are **ephemeral**: killing one, or letting it hit its timeout, discards
 * everything written inside it. State that has to outlive a sandbox belongs on a
 * {@link Volume}, which is a separate disk you mount at `/workspace` and re-attach to a
 * later sandbox.
 *
 * @example Basic usage:
 * ```ts
 * import { Sandbox } from '@lizard-build/sdk'
 *
 * const sandbox = await Sandbox.create('base', { project: 'my-project' })
 * try {
 *   await sandbox.fs.write('/tmp/hello.txt', 'hello world')
 *   const result = await sandbox.process.exec('cat /tmp/hello.txt')
 *   if (result.exitCode !== 0) throw new Error(result.stderr)
 *   console.log(result.stdout)
 * } finally {
 *   await sandbox.kill()
 * }
 * ```
 *
 * @example Carry work across sandboxes with a volume:
 * ```ts
 * const vol = await Volume.getOrCreate(projectId, 'agent-scratch', { sizeGb: 10 })
 *
 * const first = await Sandbox.create('codex', { projectId, volumeName: 'agent-scratch' })
 * await first.process.exec('echo "notes" > /workspace/notes.txt')
 * await first.kill()
 *
 * // A different sandbox, the same disk. No region to thread through: the sandbox
 * // is placed wherever the volume already lives.
 * const second = await Sandbox.create('codex', { projectId, volumeName: 'agent-scratch' })
 * console.log(await second.fs.read('/workspace/notes.txt')) // "notes"
 * ```
 */
export class Sandbox extends SandboxClient {
  protected static readonly defaultTemplate: string = 'base'
  protected static readonly defaultTimeoutMs = DEFAULT_SANDBOX_TIMEOUT_MS

  /**
   * Unique identifier of this sandbox.
   */
  readonly sandboxId: string

  /**
   * Read and write files inside the sandbox filesystem.
   *
   * @example
   * ```ts
   * await sandbox.fs.write('/app/main.py', 'print("hello")')
   * const src = await sandbox.fs.read('/app/main.py')
   * ```
   */
  readonly fs: Fs

  /**
   * Execute processes inside the sandbox.
   *
   * @example
   * ```ts
   * const { stdout } = await sandbox.process.exec('python main.py')
   * ```
   */
  readonly process: Process

  /**
   * Drive the graphical desktop of a `desktop`-template sandbox: stream it to a
   * browser, take screenshots, click and type.
   *
   * @example
   * ```ts
   * const sandbox = await Sandbox.create('desktop', { project: 'my-project' })
   * const { url } = await sandbox.desktop.start() // a credential: anyone with it controls the desktop
   * await sandbox.desktop.click(100, 200)
   * const png = await sandbox.desktop.screenshot()
   * ```
   */
  readonly desktop: Desktop

  protected readonly connectionConfig: ConnectionConfig

  constructor(opts: { sandboxId: string } & ConnectionOpts) {
    super()
    this.sandboxId = opts.sandboxId
    this.connectionConfig = new ConnectionConfig(opts)
    this.fs = new Fs(this.sandboxId, this.connectionConfig)
    this.process = new Process(this.sandboxId, this.connectionConfig)
    this.desktop = new Desktop(this.sandboxId, this.connectionConfig, this.process, this.fs)
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
   * Template availability and installed tools depend on the platform and region.
   * Use `base` for shell commands, `interpreter` for Python with the data stack
   * (use {@link CodeSandbox} to run code snippets in it), or `desktop` for a
   * graphical desktop.
   *
   * @param template Name of the sandbox template to boot from.
   *
   * @example
   * ```ts
   * const sandbox = await Sandbox.create('base', { project: 'my-project' })
   * const pythonSandbox = await Sandbox.create('interpreter', { project: 'my-project', timeoutMs: 10 * 60 * 1000 })
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
   * Connecting reads sandbox metadata without changing its state.
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
  static async list(opts?: ConnectionOpts & { projectId?: string }): Promise<SandboxInfo[]> {
    return SandboxClient.listSandboxes(opts)
  }

  /**
   * Kill the sandbox and release its resources immediately.
   *
   * @returns `true` if the sandbox was terminated, `false` if it was already gone.
   */
  async kill(opts?: ConnectionOpts): Promise<boolean> {
    return SandboxClient.killSandbox(this.sandboxId, this.resolveOpts(opts))
  }

  /**
   * Pause the sandbox: its memory, running processes and files are kept and
   * compute stops. Wait with `waitForStatus('paused')` before resuming.
   */
  async pause(opts?: ConnectionOpts): Promise<boolean> {
    return SandboxClient.pauseSandbox(this.sandboxId, this.resolveOpts(opts))
  }

  /**
   * Resume a paused sandbox exactly where it stopped, processes included. Wait
   * with `waitForStatus('running')` before running commands.
   */
  async resume(opts?: ConnectionOpts): Promise<boolean> {
    return SandboxClient.resumeSandbox(this.sandboxId, this.resolveOpts(opts))
  }

  /** Wait for an asynchronous pause/resume operation to finish. */
  async waitForStatus(status: 'paused' | 'running', opts?: SnapshotWaitOpts): Promise<SandboxInfo> {
    const deadline = Date.now() + (opts?.waitTimeoutMs ?? 600_000)
    do {
      const info = await this.getInfo(opts)
      if (info.status === status) return info
      if (['failed', 'stopped', 'deleted'].includes(info.status ?? '') || info.pauseError) {
        throw new ConflictError(info.pauseError ?? `Sandbox is ${info.status}`)
      }
      if (Date.now() >= deadline) break
      await new Promise(resolve => setTimeout(resolve, 1000))
    } while (Date.now() < deadline)
    throw new TimeoutError(`Sandbox did not become ${status} within the wait timeout`)
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
   * The token that opens this sandbox's published ports. Set by {@link getHost}
   * and {@link exposePort}; send it as the `X-Lizard-Access-Token` header.
   */
  accessToken?: string

  /**
   * Publish a port on a public HTTPS hostname and return the hostname without a scheme.
   *
   * The port is private: requests need {@link accessToken} (set by this call) as
   * the `X-Lizard-Access-Token` header, or `?lizard_token=<token>` in a browser.
   * {@link exposePort} returns the token and a ready-made browser URL together.
   *
   * @example
   * ```ts
   * // Start an HTTP server on port 3000 before exposing it.
   * const hostname = await sandbox.getHost(3000)
   * const res = await fetch(`https://${hostname}/`, {
   *   headers: { 'X-Lizard-Access-Token': sandbox.accessToken! },
   * })
   * ```
   */
  async getHost(port: number, opts?: ConnectionOpts): Promise<string> {
    return (await this.exposePort(port, opts)).hostname
  }

  /**
   * Publish a port and return everything needed to reach it: the hostname, a
   * browser `url` that carries the token, and the `accessToken` for API clients.
   *
   * @example
   * ```ts
   * const { url, hostname, accessToken } = await sandbox.exposePort(3000)
   * console.log(url) // open in a browser
   * await fetch(`https://${hostname}/api`, { headers: { 'X-Lizard-Access-Token': accessToken } })
   * ```
   */
  async exposePort(port: number, opts?: ConnectionOpts): Promise<ExposedPort> {
    const exposed = await SandboxClient.exposeSandboxPort(this.sandboxId, port, this.resolveOpts(opts))
    if (exposed.accessToken) this.accessToken = exposed.accessToken
    return exposed
  }

  /**
   * Clone this running sandbox `count` times (1-10). Each fork is a copy of the
   * microVM at this instant -- memory, running processes and files -- and is
   * billed like its source. The source keeps running.
   *
   * Returns one entry per requested fork, in order: `{ sandbox, info }`, or
   * `{ error }` for a copy that could not be made (e.g. the account's sandbox
   * limit). A sandbox with a volume attached cannot be forked (`ConflictError`, 409).
   *
   * @param opts.timeoutMs Lifetime of each fork; defaults to the source's timeout.
   *
   * @example
   * ```ts
   * const forks = await sandbox.fork({ count: 2 })
   * for (const f of forks) if (f.sandbox) await f.sandbox.process.exec('echo hi')
   * ```
   */
  async fork(opts: { count?: number; timeoutMs?: number } = {}): Promise<ForkResult<this>[]> {
    const result = await new PlatformClient(this.resolveOpts()).post<Array<{ sandbox?: SandboxInfo; error?: string }>>(
      `/api/sandboxes/${this.sandboxId}/fork`, { count: opts.count ?? 1, timeoutMs: opts.timeoutMs ?? 0 })
    const Ctor = this.constructor as new (o: { sandboxId: string } & ConnectionOpts) => this
    return (Array.isArray(result) ? result : []).map((entry): ForkResult<this> => {
      const id = entry.sandbox?.sandboxId ?? (entry.sandbox as { id?: string } | undefined)?.id
      if (!entry.sandbox || !id) return { error: entry.error ?? 'fork failed' }
      return { sandbox: new Ctor({ ...this.resolveOpts(), sandboxId: id }), info: { ...entry.sandbox, sandboxId: id } }
    })
  }

  /**
   * Save this sandbox -- memory, running processes and files -- as a private
   * snapshot. A Firecracker snapshot is `ready` as soon as this returns (about 2 s);
   * start copies of it with {@link Sandbox.restore} (about 0.4 s each). The source
   * keeps running. `poolSize` applies to container sandboxes only.
   */
  snapshot(name = `Snapshot ${this.sandboxId}`, opts: SnapshotOpts = {}): Promise<SandboxSnapshot> {
    return new PlatformClient(this.resolveOpts()).post(`/api/sandboxes/${this.sandboxId}/snapshot`, { name, poolSize: opts.poolSize ?? 5 })
  }
  unexpose(port: number): Promise<void> {
    return new PlatformClient(this.resolveOpts()).delete(`/api/sandboxes/${this.sandboxId}/expose/${port}`)
  }
  /** Stream the sandbox's logs. Not available on Firecracker sandboxes yet (`LizardError`, 501). */
  logs(opts: { tail?: number; signal?: AbortSignal } = {}) {
    return new PlatformClient(this.resolveOpts()).events(query(`/api/sandboxes/${this.sandboxId}/logs`, { tail: opts.tail }), { signal: opts.signal })
  }
  static snapshots(projectId: string, opts?: ConnectionOpts): Promise<SandboxSnapshot[]> {
    return new PlatformClient(opts ?? {}).get(`/api/projects/${encodeURIComponent(projectId)}/snapshots`)
  }
  static getSnapshot(snapshotId: string, opts?: ConnectionOpts): Promise<SandboxSnapshot> {
    return new PlatformClient(opts ?? {}).get(`/api/sandbox-snapshots/${encodeURIComponent(snapshotId)}`)
  }
  /** Start a new sandbox from a snapshot, in the snapshot's project and region. */
  static async restore(snapshotId: string, opts?: ConnectionOpts & { timeoutMs?: number }): Promise<Sandbox> {
    const client = new PlatformClient(opts ?? {})
    const snapshot = await this.getSnapshot(snapshotId, opts)
    const result = await client.post<{ id: string; sandboxId?: string }>('/api/sandboxes', {
      snapshotId, projectId: snapshot.projectId, region: snapshot.region,
      timeoutMs: opts?.timeoutMs ?? DEFAULT_SANDBOX_TIMEOUT_MS,
    })
    return new this({ ...opts, sandboxId: result.sandboxId ?? result.id })
  }
  static setSnapshotWarmPool(snapshotId: string, poolSize: number, opts?: ConnectionOpts): Promise<SandboxSnapshot> {
    return new PlatformClient(opts ?? {}).patch(`/api/sandbox-snapshots/${encodeURIComponent(snapshotId)}`, { poolSize })
  }
  /** Release idle warm copies (container snapshots); retain saved state and existing claimed sandboxes. */
  static pauseSnapshot(snapshotId: string, opts?: ConnectionOpts): Promise<SandboxSnapshot> {
    return new PlatformClient(opts ?? {}).post(`/api/sandbox-snapshots/${encodeURIComponent(snapshotId)}/pause`, {})
  }
  /** Refill the configured warm pool without another capture. */
  static resumeSnapshot(snapshotId: string, opts?: ConnectionOpts): Promise<SandboxSnapshot> {
    return new PlatformClient(opts ?? {}).post(`/api/sandbox-snapshots/${encodeURIComponent(snapshotId)}/resume`, {})
  }
  static async waitForSnapshot(snapshotId: string, opts?: SnapshotWaitOpts): Promise<SandboxSnapshot> {
    const deadline = Date.now() + (opts?.waitTimeoutMs ?? 900_000)
    do {
      const snapshot = await this.getSnapshot(snapshotId, opts)
      if (snapshot.status === 'ready' && snapshot.readyCount >= Math.max(1, snapshot.poolSize ?? 1)) return snapshot
      if (['failed', 'paused', 'suspended'].includes(snapshot.status)) throw new ConflictError(snapshot.error ?? `Snapshot is ${snapshot.status}`)
      if (Date.now() >= deadline) break
      await new Promise(resolve => setTimeout(resolve, 1000))
    } while (Date.now() < deadline)
    throw new TimeoutError('Snapshot did not become ready within the wait timeout')
  }
  static deleteSnapshot(snapshotId: string, opts?: ConnectionOpts): Promise<void> {
    return new PlatformClient(opts ?? {}).delete(`/api/sandbox-snapshots/${encodeURIComponent(snapshotId)}`)
  }

  private resolveOpts(opts?: ConnectionOpts): ConnectionOpts {
    return { ...this.connectionConfig, ...opts }
  }
}
