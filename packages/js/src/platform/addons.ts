import type { PlatformClient } from './client'

export type AddonType = 'postgres' | 'mysql' | 'mongodb' | 'mongo' | 'redis' | 's3'

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
  region?: string
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
    return this.list({ projectId }).then(items => {
      const addon = items.find(a => a.id === addonId)
      if (!addon) throw new Error('Addon not found')
      return addon
    })
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
      type: opts.type === 'mongodb' ? 'mongo' : opts.type, name: opts.name, region: opts.region,
      config: { version: opts.version,
        cpuLimit: opts.vcpu === undefined ? undefined : `${opts.vcpu * 1000}m`,
        memoryLimit: opts.memoryMb === undefined ? undefined : `${opts.memoryMb}Mi`,
        storageSize: opts.storageGb === undefined ? undefined : `${opts.storageGb}Gi` },
    })
  }

  /** Delete an addon. */
  delete(projectId: string, addonId: string): Promise<void> {
    return this.client.delete(`/api/projects/${projectId}/addons/${addonId}`)
  }

  /** Resize an addon (CPU / memory / storage). */
  async resize(projectId: string, addonId: string, opts: { vcpu?: number; memoryMb?: number; storageGb?: number }): Promise<Addon> {
    await this.client.applyConfig(projectId, {
      addons: [{ id: addonId, limits: { vcpu: opts.vcpu, memoryMb: opts.memoryMb },
        storageSize: opts.storageGb === undefined ? undefined : `${opts.storageGb}Gi` }],
    })
    return this.get(projectId, addonId)
  }

  /** Restart an addon. */
  redeploy(projectId: string, addonId: string): Promise<void> {
    return this.client.post(`/api/projects/${projectId}/addons/${addonId}/redeploy`, {})
  }
  rename(projectId: string, addonId: string, name: string): Promise<unknown> {
    return this.client.patch(`/api/projects/${projectId}/addons/${addonId}`, { name })
  }
  secrets(projectId: string, addonId: string): Promise<Array<{ key: string; value: string }>> {
    return this.client.get(`/api/projects/${projectId}/addons/${addonId}/secrets`)
  }
  logs(projectId: string, addonId: string): Promise<unknown> {
    return this.client.get(`/api/projects/${projectId}/addons/${addonId}/logs`)
  }

}
