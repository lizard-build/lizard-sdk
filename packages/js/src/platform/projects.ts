import { type PlatformClient, query } from './client'

export interface Project {
  id: string
  name: string
  slug: string
  workspaceId: string
  createdAt?: string
}

export interface CreateProjectOpts {
  workspaceId: string
  name: string
}

export class ProjectsAPI {
  constructor(private readonly client: PlatformClient) {}

  /** List all projects the API key can access. */
  list(opts?: { workspaceId?: string }): Promise<Project[]> {
    const qs = opts?.workspaceId ? `?workspaceId=${opts.workspaceId}` : ''
    return this.client.get(`/api/projects${qs}`)
  }

  /** Get a project by ID. */
  get(id: string): Promise<Project> {
    return this.client.get(`/api/projects/${id}`)
  }

  /** Create a new project. */
  create(opts: CreateProjectOpts): Promise<Project> {
    return this.client.post('/api/projects', opts)
  }

  /** Update a project's name. */
  update(id: string, opts: { name?: string }): Promise<Project> {
    return this.client.patch(`/api/projects/${id}`, opts)
  }

  /** Delete a project. */
  delete(id: string): Promise<void> {
    return this.client.delete(`/api/projects/${id}`)
  }
  apply(id: string, config: ProjectConfig): Promise<ConfigResult> {
    return this.client.applyConfig(id, config)
  }
  services(id: string): Promise<{ apps: import('./services').Service[]; addons: import('./addons').Addon[] }> {
    return this.client.get(`/api/projects/${id}/services`)
  }
  volumeLimits(id: string): Promise<Record<string, unknown>> {
    return this.client.get(`/api/projects/${id}/volume-limits`)
  }

  logs(id: string, opts: { service?: string; level?: string; limit?: number; since?: string; until?: string } = {}): Promise<import('./services').LogLine[]> {
    return this.client.get(query(`/api/projects/${id}/logs`, opts))
  }
  streamLogs(id: string, signal?: AbortSignal) { return this.client.events(`/api/projects/${id}/logs/stream`, { signal }) }

}

export interface ProjectConfig {
  revision?: number
  services?: Array<import('./services').ServiceUpdate & { id?: string; name?: string }>
  addons?: Array<{ id?: string; name?: string; instanceName?: string; type?: string; limits?: { vcpu?: number; memoryMb?: number }; storageSize?: string; config?: Record<string, unknown> }>
  secrets?: { shared?: Record<string, string | null>; services?: Record<string, Record<string, string | null>> }

}
export interface ConfigResult { revision: number; services: unknown[]; addons: unknown[]; sideEffectFailures?: unknown[] }
