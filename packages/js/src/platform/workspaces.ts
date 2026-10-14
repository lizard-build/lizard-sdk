import type { PlatformClient } from './client'
import type { PauseResult } from './projects'

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

/**
 * Resale prices: each resource's price as a multiple of Lizard's (1-100). API keys scoped
 * to the workspace see prices and costs multiplied by these; the owner's bill does not change.
 */
export interface ResaleMultipliers {
  cpu: number
  memory: number
  /** Volumes. */
  storage: number
  egress: number
  objectStorage: number
  /** Sized sandboxes' flat price. */
  sandbox: number
}

export interface ResalePricing {
  /** False when every multiplier is 1: scoped keys see Lizard's prices. */
  enabled: boolean
  multipliers: ResaleMultipliers
}

/** What a workspace may run at once (null: no limit). See {@link WorkspacesAPI.setLimits}. */
export interface WorkspaceLimits {
  /** Sandboxes running (or resuming) at once; paused ones do not count. */
  maxRunningSandboxes: number | null
  /** vCPU its apps and databases may be using right now (measured). */
  maxCpuVcpus: number | null
  /** Memory (MB) its apps and databases may be using right now (measured). */
  maxMemoryMb: number | null
}

export interface WorkspaceUsage {
  runningSandboxes: number
  /** Measured, all regions, its apps and databases. */
  cpuVcpus: number
  memoryMb: number
  /** Unix ms of the oldest reading in the sum; null when nothing was measured. */
  measuredAt: number | null
}

export interface WorkspaceLimitsInfo {
  limits: WorkspaceLimits
  usage: WorkspaceUsage
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

  /**
   * Create a workspace. The caller becomes its owner.
   *
   * Needs a key with no scopes: a scoped key gets HTTP 403 with
   * `code: 'ACCOUNT_SCOPE_REQUIRED'`.
   */
  create(opts: CreateWorkspaceOpts): Promise<Workspace> {
    return this.client.post('/api/workspaces', opts)
  }

  /**
   * Pause every app and managed database in every project of a workspace (owner only).
   * Each keeps its URL, host, port, password, settings and volumes.
   */
  pause(id: string): Promise<PauseResult> {
    return this.client.post(`/api/workspaces/${id}/pause`, {})
  }

  /** Resume what was paused in a workspace (owner only; not what a billing freeze paused). */
  resume(id: string): Promise<PauseResult> {
    return this.client.post(`/api/workspaces/${id}/resume`, {})
  }

  /**
   * The workspace's resale prices (owner only, key with no scopes).
   *
   * A scoped key gets HTTP 403 with `code: 'ACCOUNT_SCOPE_REQUIRED'`: the keys that see these
   * prices can neither read nor change them.
   */
  getResalePricing(id: string): Promise<ResalePricing> {
    return this.client.get(`/api/workspaces/${id}/resale-pricing`)
  }

  /**
   * Set the workspace's resale prices (owner only, key with no scopes). Replaces them all:
   * a resource left out is 1. Every API key scoped to the workspace, or to one of its
   * projects, then sees each price and cost multiplied (sandbox `pricePerHour`, `metrics`
   * costs, billing summaries). Display only: what Lizard bills you is unchanged.
   *
   * ```ts
   * await lizard.workspaces.setResalePricing(ws.id, { cpu: 4, memory: 4, sandbox: 4 })
   * ```
   */
  setResalePricing(id: string, multipliers: Partial<ResaleMultipliers>): Promise<ResalePricing> {
    return this.client.put(`/api/workspaces/${id}/resale-pricing`, multipliers)
  }

  /** Turn resale prices off: scoped keys see Lizard's prices again (owner only). */
  clearResalePricing(id: string): Promise<ResalePricing> {
    return this.client.put(`/api/workspaces/${id}/resale-pricing`, {})
  }

  /**
   * The workspace's limits and what it uses now. Anyone in the workspace may read them,
   * including a key scoped to it (your customer sees how close they are).
   */
  getLimits(id: string): Promise<WorkspaceLimitsInfo> {
    return this.client.get(`/api/workspaces/${id}/limits`)
  }

  /**
   * Limit what a workspace may run at once (owner only, key with no scopes). A field left out
   * stays as it is; `null` removes that limit.
   *
   * - `maxRunningSandboxes`: a create, fork or resume past it fails with HTTP 429
   *   `WORKSPACE_SANDBOX_LIMIT`.
   * - `maxCpuVcpus` / `maxMemoryMb`: what its apps and databases USE (measured every ~10 s,
   *   not their configured limits). While at or over a cap, deploys, redeploys, restarts,
   *   scale-ups, new databases and resumes there fail with HTTP 429 `WORKSPACE_USAGE_LIMIT`;
   *   services already running keep running.
   *
   * ```ts
   * await lizard.workspaces.setLimits(ws.id, { maxRunningSandboxes: 5, maxCpuVcpus: 2, maxMemoryMb: 4096 })
   * ```
   */
  setLimits(id: string, limits: Partial<WorkspaceLimits>): Promise<WorkspaceLimitsInfo> {
    return this.client.put(`/api/workspaces/${id}/limits`, limits)
  }

  /**
   * Delete a workspace.
   *
   * Empty-only by default — the server refuses while any project, sandbox or volume
   * remains, so this cannot quietly destroy a user's work. `{ force: true }` deletes
   * the workspace with its apps, addons and projects; that is irreversible. It does not
   * delete sandboxes, sandbox volumes or snapshots: a running sandbox keeps running with
   * no workspace left to find it in. Kill the workspace's sandboxes and delete its
   * volumes and snapshots first.
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
