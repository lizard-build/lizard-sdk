import { PlatformClient, query } from '../platform/client'
import { ConnectionConfig, ConnectionOpts, DEFAULT_SANDBOX_TIMEOUT_MS } from '../config'
import { Process } from './process'
import { Fs } from './fs'
import { Desktop } from './desktop'
import { SandboxClient, SandboxInfo, SandboxOpts, ExposedPort } from './client'
import { TimeoutError, ConflictError } from '../errors'

/** The server allows a snapshot 10 minutes (its memory upload); a little more here. */
const SNAPSHOT_TIMEOUT_MS = 11 * 60_000

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
  /**
   * Always `'project'`: every snapshot restores only in its own project.
   * @deprecated Kept because the server still returns it; it no longer tells you anything.
   */
  scope: SnapshotScope
  /** Whether the source had a volume attached (a restore then cannot attach another); `null` for older snapshots, which cannot take one. */
  sourceVolume: boolean | null
  /** The user who took it; `null` for snapshots from before snapshots belonged to a user. */
  createdBy: string | null
}
/**
 * Where a snapshot may be restored. Every snapshot restores only in its own project and region,
 * so this is always `'project'`; `'user'` and `'workspace'` remain only so old code compiles.
 * @deprecated Every snapshot restores only in its own project; always `'project'`.
 */
/** What a schedule runs and when: `every` ("5m", "1h") or `cron` ("*\/5 * * * *"), and `prompt` or `command`. */
export interface ScheduleOpts {
  every?: string | number
  cron?: string
  /** IANA time zone for `cron` (default UTC). */
  timezone?: string
  /** Run the coding agent with this prompt; each run is a new conversation. */
  prompt?: string
  /** Or run this shell command (in /workspace, as root; success = exit code 0). */
  command?: string
  agent?: string
  model?: string | null
  reasoningEffort?: 'minimal' | 'low' | 'medium' | 'high' | 'xhigh' | null
  /** Stop a run after this many seconds (default 600). */
  timeoutSeconds?: number
  /** Sleep with memory between runs (processes and open apps survive; slower pause). Default false: files only. */
  keepMemory?: boolean
  name?: string | null
  enabled?: boolean
}

export interface SandboxSchedule {
  id: string
  sandboxId: string
  name: string | null
  every: string | null
  everySeconds: number | null
  cron: string | null
  timezone: string
  kind: 'prompt' | 'command'
  prompt: string | null
  command: string | null
  agent: string | null
  model: string | null
  reasoningEffort: string | null
  timeoutSeconds: number
  keepMemory: boolean
  enabled: boolean
  disabledReason: string | null
  nextRunAt: string | null
  running: boolean
  lastRunAt: string | null
  lastStatus: string | null
  consecutiveFailures: number
  skippedCount: number
}

export interface SandboxScheduleRun {
  id: string
  scheduleId: string
  sandboxId: string
  status: 'running' | 'succeeded' | 'failed' | 'timeout' | 'interrupted'
  woke: boolean
  slept: boolean
  startedAt: string
  /** Set once the run is over and its sandbox is back asleep (if the run woke it). */
  endedAt: string | null
  /** endedAt is set. */
  finished: boolean
  durationMs: number | null
  exitCode: number | null
  promptId: string | null
  conversationId: string | null
  output: string | null
  error: string | null
}

export type SnapshotScope = 'user' | 'workspace' | 'project'
export interface SnapshotOpts {
  /** Warm copies to keep ready for an older snapshot. Firecracker snapshots ignore it: they restore from disk. */
  poolSize?: number
  /**
   * Ignored and not sent: every snapshot restores only in its own project.
   * @deprecated Every snapshot restores only in its own project; always `'project'`.
   */
  scope?: SnapshotScope
  /** Also save memory and running processes: sandboxes started from it continue where this one was
   *  (slower to take, the more RAM is in use). Default (the platform's): files only, about a second;
   *  sandboxes started from it boot fresh. `fast: true` is the same as the default. */
  full?: boolean
  fast?: boolean
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
   * Pause the sandbox: compute stops and its files are kept. Wait with
   * `waitForStatus('paused')` before resuming. By default (the platform's) the
   * pause keeps files only: about a second whatever the RAM, running processes
   * end and the resume boots the sandbox fresh. `{ full: true }` also keeps memory
   * and running processes (slower the more RAM is in use), so the resume picks up
   * exactly where it stopped. `{ fast: true }` is the same as the default pause;
   * `memory: true/false` is the same as `full`/`fast`.
   */
  async pause(opts?: ConnectionOpts & { fast?: boolean; full?: boolean; memory?: boolean }): Promise<boolean> {
    return SandboxClient.pauseSandbox(this.sandboxId, this.resolveOpts(opts))
  }

  /**
   * Resume a paused sandbox: with its processes after a `full` pause, booted fresh
   * with its files after a default (files-only) pause. Wait
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
   * Clone this running sandbox `count` times (1-100). Each fork is a copy of the
   * microVM at this instant -- memory, running processes and files -- and is
   * billed like its source. The source keeps running. Each copy counts as a
   * sandbox start, so the account's running-sandbox limit is the real cap.
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
   * Save this sandbox as a private snapshot. By default (the platform's) it saves the files:
   * about a second whatever the RAM, and sandboxes started from it boot fresh with them.
   * `{ full: true }` also saves memory and running processes, so sandboxes started from it
   * continue where this one was; that takes longer the more RAM is in use (its memory is
   * uploaded first), so the call waits up to 11 minutes. The answer's `withMemory` says what
   * was kept. Start copies with {@link Sandbox.restore}, in this sandbox's project: a snapshot
   * restores only in its own project. The source keeps running. Firecracker snapshots ignore
   * `poolSize`. `scope` is ignored and not sent.
   */
  snapshot(name = `Snapshot ${this.sandboxId}`, opts: SnapshotOpts = {}): Promise<SandboxSnapshot> {
    if (opts.full === true && opts.fast === true) throw new Error('snapshot: use either fast or full, not both')
    // Sent as memory: true/false, which servers older than the "full" name accept.
    const memory = opts.full === true ? true : opts.fast === true ? false : undefined
    // opts.scope is not sent: every snapshot restores only in its own project.
    return new PlatformClient(this.resolveOpts()).post(`/api/sandboxes/${this.sandboxId}/snapshot`, { name, poolSize: opts.poolSize ?? 5, ...(memory !== undefined ? { memory } : {}) }, SNAPSHOT_TIMEOUT_MS)
  }
  unexpose(port: number): Promise<void> {
    return new PlatformClient(this.resolveOpts()).delete(`/api/sandboxes/${this.sandboxId}/expose/${port}`)
  }
  /** Stream the sandbox's logs. Not available yet (`LizardError`, 501). */
  logs(opts: { tail?: number; signal?: AbortSignal } = {}) {
    return new PlatformClient(this.resolveOpts()).events(query(`/api/sandboxes/${this.sandboxId}/logs`, { tail: opts.tail }), { signal: opts.signal })
  }
  static snapshots(projectId: string, opts?: ConnectionOpts): Promise<SandboxSnapshot[]> {
    return new PlatformClient(opts ?? {}).get(`/api/projects/${encodeURIComponent(projectId)}/snapshots`)
  }
  /** Every snapshot you took, across all your workspaces and projects. */
  static mySnapshots(opts?: ConnectionOpts): Promise<SandboxSnapshot[]> {
    return new PlatformClient(opts ?? {}).get('/api/sandbox-snapshots')
  }
  static getSnapshot(snapshotId: string, opts?: ConnectionOpts): Promise<SandboxSnapshot> {
    return new PlatformClient(opts ?? {}).get(`/api/sandbox-snapshots/${encodeURIComponent(snapshotId)}`)
  }
  /**
   * Start a new sandbox from a snapshot, in its own project and region. A `projectId` for any
   * other project fails with 403 (`SNAPSHOT_SCOPE`). `volumeId` mounts that volume at `/workspace`
   * (a Firecracker snapshot of a sandbox that had no volume attached; the volume must be in the
   * snapshot's project and region).
   */
  static async restore(snapshotId: string, opts?: ConnectionOpts & { timeoutMs?: number; projectId?: string; volumeId?: string }): Promise<Sandbox> {
    const client = new PlatformClient(opts ?? {})
    const snapshot = await this.getSnapshot(snapshotId, opts)
    const result = await client.post<{ id: string; sandboxId?: string }>('/api/sandboxes', {
      snapshotId, projectId: opts?.projectId ?? (opts?.volumeId ? undefined : snapshot.projectId), region: snapshot.region,
      volumeId: opts?.volumeId,
      timeoutMs: opts?.timeoutMs ?? DEFAULT_SANDBOX_TIMEOUT_MS,
    })
    return new this({ ...opts, sandboxId: result.sandboxId ?? result.id })
  }
  /**
   * Changes nothing: every snapshot restores only in its own project. The server accepts the call
   * and returns the snapshot as it is, with `scope: 'project'`.
   * @deprecated Every snapshot restores only in its own project; kept so old code keeps running.
   */
  static setSnapshotScope(snapshotId: string, scope: SnapshotScope, opts?: ConnectionOpts): Promise<SandboxSnapshot> {
    return new PlatformClient(opts ?? {}).patch(`/api/sandbox-snapshots/${encodeURIComponent(snapshotId)}`, { scope })
  }
  static setSnapshotWarmPool(snapshotId: string, poolSize: number, opts?: ConnectionOpts): Promise<SandboxSnapshot> {
    return new PlatformClient(opts ?? {}).patch(`/api/sandbox-snapshots/${encodeURIComponent(snapshotId)}`, { poolSize })
  }
  /** Release idle warm copies of an older snapshot; retain saved state and existing claimed sandboxes. Firecracker snapshots have no warm copies. */
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

  /**
   * Run a prompt or a command in this sandbox on a schedule. Each run wakes the sandbox if it is
   * paused, runs, and puts it back to sleep (files only unless `keepMemory`); a sandbox that was
   * already running is left running. You pay only while it is awake.
   *
   * ```ts
   * await sandbox.schedule({ every: '5m', prompt: 'Continue the research in /workspace/research' })
   * await sandbox.schedule({ cron: '0 9 * * mon-fri', timezone: 'Europe/Berlin', command: './report.sh' })
   * ```
   */
  schedule(opts: ScheduleOpts): Promise<SandboxSchedule> {
    return new PlatformClient(this.resolveOpts()).post(`/api/sandboxes/${this.sandboxId}/schedules`, opts)
  }
  /** This sandbox's schedules. */
  async schedules(): Promise<SandboxSchedule[]> {
    return (await new PlatformClient(this.resolveOpts()).get<{ schedules: SandboxSchedule[] }>(`/api/sandboxes/${this.sandboxId}/schedules`)).schedules
  }
  /** Every schedule you can see, or one sandbox's with `sandboxId`. */
  static async listSchedules(opts: ConnectionOpts & { sandboxId?: string } = {}): Promise<SandboxSchedule[]> {
    return (await new PlatformClient(opts).get<{ schedules: SandboxSchedule[] }>(query('/api/sandbox-schedules', { sandboxId: opts.sandboxId }))).schedules
  }
  static getSchedule(scheduleId: string, opts?: ConnectionOpts): Promise<SandboxSchedule> {
    return new PlatformClient(opts ?? {}).get(`/api/sandbox-schedules/${encodeURIComponent(scheduleId)}`)
  }
  /** Change any of the schedule's settings; `{ enabled: false }` switches it off. */
  static updateSchedule(scheduleId: string, patch: ScheduleOpts, opts?: ConnectionOpts): Promise<SandboxSchedule> {
    return new PlatformClient(opts ?? {}).patch(`/api/sandbox-schedules/${encodeURIComponent(scheduleId)}`, patch)
  }
  static deleteSchedule(scheduleId: string, opts?: ConnectionOpts): Promise<void> {
    return new PlatformClient(opts ?? {}).delete(`/api/sandbox-schedules/${encodeURIComponent(scheduleId)}`)
  }
  /** Run the schedule now (within a few seconds); also switches it back on. */
  static runSchedule(scheduleId: string, opts?: ConnectionOpts): Promise<SandboxSchedule> {
    return new PlatformClient(opts ?? {}).post(`/api/sandbox-schedules/${encodeURIComponent(scheduleId)}/run`, {})
  }
  /** The schedule's recent runs, newest first. */
  static async scheduleRuns(scheduleId: string, opts: ConnectionOpts & { limit?: number } = {}): Promise<SandboxScheduleRun[]> {
    return (await new PlatformClient(opts).get<{ runs: SandboxScheduleRun[] }>(query(`/api/sandbox-schedules/${encodeURIComponent(scheduleId)}/runs`, { limit: opts.limit }))).runs
  }

  private resolveOpts(opts?: ConnectionOpts): ConnectionOpts {
    return { ...this.connectionConfig, ...opts }
  }
}
