import type { PlatformClient } from './client'

export type AddonType = 'postgres' | 'mysql' | 'mongodb' | 'redis' | 's3'

export interface Addon {
  id: string
  name: string
  type: AddonType
  projectId: string
  status: 'none' | 'running' | 'crashed' | 'stopped'
  deployStatus: string
  version?: string
  /** Exposed connection variables (e.g. DATABASE_URL, REDIS_URL). */
  env?: Record<string, string>
}

export interface CreateAddonOpts {
  projectId: string
  type: AddonType
  name?: string
  version?: string
  /** vCPU count */
  vcpu?: number
  /** Memory in MB */
  memoryMb?: number
  /** Storage in GB */
  storageGb?: number
}

export class AddonsAPI {
  constructor(private readonly client: PlatformClient) {}

  /** List all addons in a project. */
  list(opts: { projectId: string }): Promise<Addon[]> {
    return this.client.get(`/api/projects/${opts.projectId}/addons`)
  }

  /** Get an addon by ID. */
  get(projectId: string, addonId: string): Promise<Addon> {
    return this.client.get(`/api/projects/${projectId}/addons/${addonId}`)
  }

  /**
   * Create a new managed addon (database, cache, or object store).
   *
   * @example
   * ```ts
   * const pg = await lizard.addons.create({ projectId, type: 'postgres' })
   * // Inject into a service:
   * await lizard.secrets.set({ serviceId: svcId, key: 'DATABASE_URL', value: `${{${pg.name}.DATABASE_URL}}` })
   * ```
   */
  create(opts: CreateAddonOpts): Promise<Addon> {
    return this.client.post(`/api/projects/${opts.projectId}/addons`, {
      type: opts.type,
      name: opts.name,
      version: opts.version,
      vcpu: opts.vcpu,
      memoryMb: opts.memoryMb,
      storageGb: opts.storageGb,
    })
  }

  /** Delete an addon. */
  delete(projectId: string, addonId: string): Promise<void> {
    return this.client.delete(`/api/projects/${projectId}/addons/${addonId}`)
  }

  /** Resize an addon (CPU / memory / storage). */
  resize(projectId: string, addonId: string, opts: { vcpu?: number; memoryMb?: number; storageGb?: number }): Promise<Addon> {
    return this.client.post(`/api/projects/${projectId}/addons/${addonId}/resize`, opts)
  }

  /** Restart an addon VM. */
  redeploy(projectId: string, addonId: string): Promise<void> {
    return this.client.post(`/api/projects/${projectId}/addons/${addonId}/redeploy`, {})
  }
}
