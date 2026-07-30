import type { PlatformClient } from './client'

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
}
