import { ConnectionConfig, type ConnectionOpts } from './config'
import { LizardError } from './errors'
import { resolveProjectId } from './project'
import { Sandbox } from './sandbox'
import type { SandboxInfo, SandboxOpts } from './sandbox/client'
import { PlatformClient } from './platform/client'
import { ProjectsAPI } from './platform/projects'
import { ServicesAPI } from './platform/services'
import { AddonsAPI } from './platform/addons'
import { SecretsAPI } from './platform/secrets'
import { DomainsAPI } from './platform/domains'
import { MetricsAPI } from './platform/metrics'
import { WorkspacesAPI } from './platform/workspaces'
import { ApiKeysAPI } from './platform/api-keys'
import { RegionsAPI } from './platform/regions'
import { BillingAPI } from './platform/billing'
import { Volume } from './volume'
import type { CreateVolumeOpts, VolumeInfo } from './volume'

export interface LizardOpts extends ConnectionOpts {
  /**
   * The project every sandbox created through this client belongs to — its ID,
   * slug, or name. Required for sandbox operations; optional for platform
   * management (projects, services, addons, etc.).
   */
  project?: string
}

/**
 * The Lizard client — entry point for sandboxes and platform management.
 *
 * @example Sandbox usage (backward-compatible)
 * ```ts
 * const lizard = new Lizard({ project: 'my-project' })
 * const sandbox = await lizard.create('base')
 * await sandbox.process.exec('echo hello')
 * await sandbox.kill()
 * ```
 *
 * @example Platform management
 * ```ts
 * const lizard = new Lizard({ apiKey: process.env.LIZARD_API_KEY })
 *
 * // Deploy from git
 * const deploy = await lizard.services.deploy({ projectId, name: 'api', repoUrl: '...', branch: 'main' })
 * const result = await deploy.wait()
 * console.log('Deployed to', result.url)
 *
 * // Add a Postgres addon and wire it to the service
 * const pg = await lizard.addons.create({ projectId, type: 'postgres' })
 * await lizard.secrets.set(projectId, {
 *   serviceId: result.serviceId,
 *   key: 'DATABASE_URL',
 *   value: `${{${pg.name}.DATABASE_URL}}`,
 * })
 * ```
 */
export class Lizard {
  private readonly config: ConnectionConfig
  private readonly projectRef: string | undefined
  private _platform: PlatformClient | undefined

  // ── Platform namespace APIs ───────────────────────────────────────────────
  /** Create, list and delete workspaces — the top of the ownership tree. */
  readonly workspaces: WorkspacesAPI
  /** Mint and revoke API keys, including keys scoped to one workspace or project. */
  readonly apiKeys: ApiKeysAPI
  /** List the regions workloads can be placed in. */
  readonly regions: RegionsAPI
  /** Account balance, burn rate and transactions. */
  readonly billing: BillingAPI
  /** Manage projects. */
  readonly projects: ProjectsAPI
  /** Deploy and manage services. */
  readonly services: ServicesAPI
  /** Manage addons (postgres, redis, s3, mysql, mongodb). */
  readonly addons: AddonsAPI
  /** Manage secrets and environment variables. */
  readonly secrets: SecretsAPI
  /** Manage custom domains. */
  readonly domains: DomainsAPI
  /** Query CPU, memory, network, disk, and cost metrics. */
  readonly metrics: MetricsAPI

  constructor(opts: LizardOpts) {
    this.config = new ConnectionConfig(opts)
    this.projectRef = opts.project
    const platform = new PlatformClient(opts)
    this._platform = platform
    this.workspaces = new WorkspacesAPI(platform)
    this.apiKeys = new ApiKeysAPI(platform)
    this.regions = new RegionsAPI(platform)
    this.billing = new BillingAPI(platform)
    this.projects = new ProjectsAPI(platform)
    this.services = new ServicesAPI(platform)
    this.addons = new AddonsAPI(platform)
    this.secrets = new SecretsAPI(platform)
    this.domains = new DomainsAPI(platform)
    this.metrics = new MetricsAPI(platform)
  }

  // ── Sandbox convenience methods (backward-compatible) ──────────────────

  /** Resolve the client's project reference to a stable project ID (cached). */
  async projectId(): Promise<string> {
    if (!this.projectRef) throw new LizardError('No project set. Pass project in Lizard({ project }) to use sandbox APIs.')
    return resolveProjectId(this.projectRef, this.config)
  }

  private async connectionOpts(extra?: ConnectionOpts): Promise<ConnectionOpts> {
    return { apiKey: this.config.apiKey, apiUrl: this.config.apiUrl, ...extra }
  }

  /**
   * Create a new sandbox in this client's project.
   * @requires `project` to be set in the constructor.
   */
  async create(template?: string, opts?: Omit<SandboxOpts, 'project' | 'projectId'>): Promise<Sandbox> {
    const projectId = await this.projectId()
    const sandboxOpts: SandboxOpts = { ...opts, ...(await this.connectionOpts()), projectId }
    return template ? Sandbox.create(template, sandboxOpts) : Sandbox.create(sandboxOpts)
  }

  /** Connect to an existing sandbox by ID. Throws `NotFoundError` if it is gone. */
  async connect(sandboxId: string, opts?: ConnectionOpts): Promise<Sandbox> {
    return Sandbox.connect(sandboxId, await this.connectionOpts(opts))
  }

  /** List running sandboxes for the authenticated account. */
  async list(opts?: ConnectionOpts): Promise<SandboxInfo[]> {
    return Sandbox.list(await this.connectionOpts(opts))
  }

  // ── Volumes, bound to this client's project ───────────────────────────────

  /**
   * Persistent volumes in this client's project.
   *
   * The same calls as the static {@link Volume} methods, minus the `projectId`
   * argument — the client already knows it.
   *
   * @requires `project` to be set in the constructor.
   *
   * @example
   * ```ts
   * const lizard = new Lizard({ project: 'my-project' })
   * const vol = await lizard.volumes.getOrCreate('scratch', { sizeGb: 10 })
   * const sb  = await lizard.create('codex', { volumeName: 'scratch' })
   * ```
   */
  readonly volumes = {
    create: async (name: string, opts?: CreateVolumeOpts): Promise<Volume> =>
      Volume.create(await this.projectId(), name, { ...(await this.connectionOpts()), ...opts }),
    getOrCreate: async (name: string, opts?: CreateVolumeOpts): Promise<Volume> =>
      Volume.getOrCreate(await this.projectId(), name, { ...(await this.connectionOpts()), ...opts }),
    get: async (nameOrId: string, opts?: ConnectionOpts): Promise<Volume> =>
      Volume.get(await this.projectId(), nameOrId, { ...(await this.connectionOpts()), ...opts }),
    list: async (opts?: ConnectionOpts): Promise<VolumeInfo[]> =>
      Volume.list(await this.projectId(), { ...(await this.connectionOpts()), ...opts }),
    delete: async (nameOrId: string, opts?: ConnectionOpts): Promise<void> =>
      Volume.delete(await this.projectId(), nameOrId, { ...(await this.connectionOpts()), ...opts }),
  }

  // ── Account ───────────────────────────────────────────────────────────────

  /**
   * The account this credential belongs to — the SDK's `lizard whoami`.
   *
   * A **scoped** key gets identity only: `id`, `username`, `avatarUrl`, `scoped: true`
   * and the key's own `scopes`. The account's email, balance, plan and billing status
   * are withheld — they belong to the account, not to the key holder, and a scoped key
   * is meant to be handed to an end user or injected into a sandbox. An unscoped key
   * or a session sees the full account.
   *
   * Reading back `scopes` is the cheapest way to answer "what can this key reach".
   */
  async whoami(): Promise<Account> {
    return this.platform.get<Account>('/api/auth/me')
  }

  /** The underlying HTTP client, for endpoints this SDK does not wrap yet. */
  get platform(): PlatformClient {
    return this._platform!
  }
}

/**
 * The account behind a credential — see {@link Lizard.whoami}.
 *
 * Everything past `avatarUrl` is present only for an unscoped key or a session; a
 * scoped key gets `scoped: true` and `scopes` in their place.
 */
export interface Account {
  id: string
  username: string
  avatarUrl?: string | null
  /** True when the calling key is scoped, meaning the account fields below are absent. */
  scoped?: boolean
  /** What the calling key may reach. Present when `scoped` is true. */
  scopes?: Array<{ type: 'workspace' | 'project'; id: string }>
  email?: string | null
  plan?: string
  billingStatus?: string
  balanceCents?: number
}
