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

  /** Connect to an existing sandbox by ID (resumes it if paused). */
  async connect(sandboxId: string, opts?: ConnectionOpts): Promise<Sandbox> {
    return Sandbox.connect(sandboxId, await this.connectionOpts(opts))
  }

  /** List running sandboxes for the authenticated account. */
  async list(opts?: ConnectionOpts): Promise<SandboxInfo[]> {
    return Sandbox.list(await this.connectionOpts(opts))
  }
}
