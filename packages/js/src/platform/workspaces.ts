import type { PlatformClient } from './client'

export interface Workspace {
  id: string
  name: string
  slug: string
  /** `owner` | `admin` | `member` — the calling account's role in this workspace. */
  role?: string
  /** True for the account's own workspace, which cannot be deleted. */
  isPersonal?: boolean
  projectCount?: number
  plan?: string
  createdAt?: number | string
}

export interface CreateWorkspaceOpts {
  name: string
}

/**
 * Workspaces — the top of the ownership tree: a workspace holds projects, a project
 * holds services, sandboxes and volumes.
 *
 * This is the missing first step of per-user provisioning. Handing each of your users
 * their own workspace, plus an API key scoped to it, is what keeps them isolated from
 * one another while all of it bills to your account:
 *
 * ```ts
 * const ws  = await lizard.workspaces.create({ name: `user-${userId}` })
 * const prj = await lizard.projects.create({ workspaceId: ws.id, name: 'default' })
 * const key = await lizard.apiKeys.create({ name: `user-${userId}`, workspaces: [ws.id] })
 * // hand key.key to that user — it reaches nothing outside ws
 * ```
 *
 * @see {@link ApiKeysAPI} for the scoping half of that flow.
 */
export class WorkspacesAPI {
  constructor(private readonly client: PlatformClient) {}

  /**
   * List workspaces the calling credential can see.
   *
   * A scoped API key sees only what it is scoped to: a workspace-scoped key returns
   * that one workspace, and a project-scoped key returns the workspace containing its
   * project. A full key returns every workspace the account belongs to.
   */
  list(): Promise<Workspace[]> {
    return this.client.get('/api/workspaces')
  }

  /** Create a workspace. The caller becomes its owner. */
  create(opts: CreateWorkspaceOpts): Promise<Workspace> {
    return this.client.post('/api/workspaces', opts)
  }

  /**
   * Delete a workspace.
   *
   * Empty-only by default — the server refuses while any project or sandbox remains,
   * so this cannot quietly destroy a user's work. Pass `{ force: true }` to delete a
   * workspace and everything in it; that is irreversible.
   */
  delete(id: string, opts?: { force?: boolean }): Promise<void> {
    const qs = opts?.force ? '' : '?requireEmpty=true'
    return this.client.delete(`/api/workspaces/${id}${qs}`)
  }

  /**
   * Find a workspace by name, slug, or id, or `null` if there is no such workspace.
   * Matching is exact; id wins, then slug, then name.
   */
  async find(nameOrSlugOrId: string): Promise<Workspace | null> {
    const all = await this.list()
    return (
      all.find(w => w.id === nameOrSlugOrId) ??
      all.find(w => w.slug === nameOrSlugOrId) ??
      all.find(w => w.name === nameOrSlugOrId) ??
      null
    )
  }
}
