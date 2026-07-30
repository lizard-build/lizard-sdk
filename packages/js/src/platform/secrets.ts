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
    const tasks: Promise<unknown>[] = []
    if (Object.keys(projectScoped).length > 0) {
      tasks.push(this.client.post(`/api/projects/${projectId}/secrets`, projectScoped))
    }
    for (const [serviceId, kv] of byService) {
      tasks.push(this.client.post(`/api/apps/${serviceId}/secrets`, kv))
    }
    await Promise.all(tasks)
  }

  /** Delete a secret by key. */
  async delete(projectId: string, opts: { key: string; serviceId?: string }): Promise<void> {
    if (opts.serviceId) {
      await this.client.delete(`/api/apps/${opts.serviceId}/secrets`, { key: opts.key })
    } else {
      await this.client.delete(`/api/projects/${projectId}/secrets`, { key: opts.key })
    }
  }
}
