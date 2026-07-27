import { ConnectionConfig, ConnectionOpts } from './config'
import { LizardError } from './errors'
import { resolveProjectId } from './project'
import { Sandbox } from './sandbox'
import type { SandboxInfo, SandboxOpts } from './sandbox/client'

export interface LizardOpts extends ConnectionOpts {
  /**
   * The project every sandbox created through this client belongs to — its ID,
   * slug, or name. Required: sandboxes are billed per project, so a project-less
   * sandbox cannot be created.
   */
  project: string
}

/**
 * The Lizard client — the entry point for creating sandboxes.
 *
 * A client is pinned to one project (billing is metered per project), so every
 * sandbox it creates is attributed correctly. The project reference — ID, slug,
 * or name — is resolved to a project ID on first use and cached.
 *
 * @example
 * ```ts
 * import { Lizard } from '@lizard-build/sdk'
 *
 * const lizard = new Lizard({ project: 'my-project' }) // apiKey from LIZARD_API_KEY
 *
 * const sandbox = await lizard.create('base')
 * await sandbox.process.exec('echo hello')
 * await sandbox.kill()
 * ```
 */
export class Lizard {
  private readonly config: ConnectionConfig
  private readonly projectRef: string

  constructor(opts: LizardOpts) {
    if (!opts?.project) {
      throw new LizardError(
        'A project is required. Pass project (its ID, slug, or name): new Lizard({ project: "my-project" }).'
      )
    }
    this.config = new ConnectionConfig(opts)
    this.projectRef = opts.project
  }

  /** Resolve the client's project reference to a stable project ID (cached). */
  async projectId(): Promise<string> {
    return resolveProjectId(this.projectRef, this.config)
  }

  private async connectionOpts(extra?: ConnectionOpts): Promise<ConnectionOpts> {
    return { apiKey: this.config.apiKey, apiUrl: this.config.apiUrl, ...extra }
  }

  /**
   * Create a new sandbox in this client's project.
   *
   * @example
   * ```ts
   * const sandbox = await lizard.create('base')
   * const sandbox = await lizard.create('code-interpreter-v1', { timeoutMs: 600_000 })
   * ```
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
