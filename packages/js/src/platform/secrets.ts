import type { PlatformClient } from './client'

export interface Secret {
  key: string
  value: string
}

export interface SetSecretOpts {
  key: string
  value: string
  /** Target a specific service. Omit for project-scope. */
  serviceId?: string
  /** If true, set at project scope (shared across all services). */
  global?: boolean
}

export interface ListSecretsOpts {
  serviceId?: string
}

export class SecretsAPI {
  constructor(private readonly client: PlatformClient) {}

  /**
   * List secrets for a project or service.
   *
   * @param projectId - The project ID.
   * @param opts.serviceId - If given, list service-scoped secrets instead of project secrets.
   */
  list(projectId: string, opts?: ListSecretsOpts): Promise<Secret[]> {
    if (opts?.serviceId) {
      return this.client.get(`/api/apps/${opts.serviceId}/secrets`)
    }
    return this.client.get(`/api/projects/${projectId}/secrets`)
  }

  /**
   * Set one or more secrets.
   *
   * ```ts
   * // Service-scoped secret (default):
   * await lizard.secrets.set(projectId, { key: 'DATABASE_URL', value: '${{postgres.DATABASE_URL}}', serviceId })
   *
   * // Project-scoped (shared across all services):
   * await lizard.secrets.set(projectId, { key: 'LOG_LEVEL', value: 'info', global: true })
   * ```
   */
  async set(projectId: string, secrets: SetSecretOpts | SetSecretOpts[]): Promise<void> {
    const items = Array.isArray(secrets) ? secrets : [secrets]
    // Group by scope
    const byService = new Map<string, Record<string, string>>()
    const projectScoped: Record<string, string> = {}
    for (const s of items) {
      if (s.global || !s.serviceId) {
        projectScoped[s.key] = s.value
      } else {
        if (!byService.has(s.serviceId)) byService.set(s.serviceId, {})
        byService.get(s.serviceId)![s.key] = s.value
      }
    }
    const services: Record<string, Record<string, string | null>> = {}
    for (const [id, values] of byService) {
      const svc = await this.client.get<{ name: string; projectId: string }>(`/api/apps/${id}`)
      if (svc.projectId !== projectId) throw new Error('Service does not belong to this project')
      services[svc.name] = values
    }
    await this.client.applyConfig(projectId, { secrets: { shared: projectScoped, services } })
  }
  async delete(projectId: string, opts: { key: string; serviceId?: string }): Promise<void> {
    const secrets: { shared?: Record<string, null>; services?: Record<string, Record<string, null>> } = {}
    if (opts.serviceId) {
      const svc = await this.client.get<{ name: string; projectId: string }>(`/api/apps/${opts.serviceId}`)
      if (svc.projectId !== projectId) throw new Error('Service does not belong to this project')
      secrets.services = { [svc.name]: { [opts.key]: null } }
    } else secrets.shared = { [opts.key]: null }
    await this.client.applyConfig(projectId, { secrets })
  }
  refs(projectId: string, serviceId?: string): Promise<unknown> {
    return this.client.get(serviceId ? `/api/apps/${serviceId}/variables:refs` : `/api/projects/${projectId}/variables:refs`)
  }
}
