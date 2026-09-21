import type { PlatformClient } from './client'

export interface ApiKeyScope {
  type: 'workspace' | 'project'
  id: string
  /** Present on read; the server resolves the scoped resource's name for display. */
  name?: string
}

export interface ApiKey {
  id: string
  name: string
  /** A masked fragment, e.g. `liz_abc…xyz`. The full key is only ever returned once. */
  keyPreview?: string
  scopes: ApiKeyScope[]
  createdAt?: number | string | null
  lastUsedAt?: number | string | null
}

export interface CreatedApiKey extends ApiKey {
  /**
   * The full `liz_` secret. **Returned exactly once, by this create call** — it is
   * stored hashed and no later request can read it back. Hand it to its owner or
   * persist it here, or it is gone.
   */
  key: string
}

export interface CreateApiKeyOpts {
  name: string
  /** Workspace ids this key may reach. */
  workspaces?: string[]
  /** Project ids this key may reach. */
  projects?: string[]
  /** Raw scope list, if you would rather build it yourself than use the two above. */
  scopes?: ApiKeyScope[]
}

/**
 * API keys, including the scoped keys that make per-user isolation possible.
 *
 * **A key with no scope has full access** to every workspace and project the creating
 * account can reach. Pass `workspaces` or `projects` to bound it. Scopes are enforced
 * server-side on every route, so a scoped key that leaks — out of a sandbox, a log, a
 * user's machine — reaches only what it was scoped to.
 *
 * A scoped key cannot mint a broader key: that check is server-side and exact, so
 * handing a user a workspace-scoped key is not a step away from full access.
 *
 * @example Give each of your users their own isolated workspace
 * ```ts
 * const ws  = await lizard.workspaces.create({ name: `user-${userId}` })
 * const prj = await lizard.projects.create({ workspaceId: ws.id, name: 'default' })
 * const key = await lizard.apiKeys.create({ name: `user-${userId}`, workspaces: [ws.id] })
 *
 * // key.key is visible only here. Store it now.
 * await db.users.update(userId, { lizardKey: key.key })
 * ```
 *
 * @example Let a sandbox use the CLI as that user, and nothing more
 * ```ts
 * const sandbox = await Sandbox.create('codex', {
 *   projectId: prj.id,
 *   lizardToken: key.key, // scoped — safe to expose to code in the sandbox
 * })
 * await sandbox.process.exec('lizard volume list')
 * ```
 */
export class ApiKeysAPI {
  constructor(private readonly client: PlatformClient) {}

  /** List the account's API keys. Previews only — full keys are never returned here. */
  list(): Promise<ApiKey[]> {
    return this.client.get('/api/account/api-keys')
  }

  /**
   * Create an API key.
   *
   * The response is the only place the full key appears. Omitting every scope creates
   * a full-access key; the server rejects an attempt to create one from a key that is
   * itself scoped.
   */
  create(opts: CreateApiKeyOpts): Promise<CreatedApiKey> {
    const scopes: ApiKeyScope[] = [
      ...(opts.scopes ?? []),
      ...(opts.workspaces ?? []).map(id => ({ type: 'workspace' as const, id })),
      ...(opts.projects ?? []).map(id => ({ type: 'project' as const, id })),
    ]
    return this.client.post('/api/account/api-keys', { name: opts.name, scopes })
  }

  /** Revoke a key by id. It stops working immediately, everywhere. */
  delete(id: string): Promise<void> {
    return this.client.delete(`/api/account/api-keys/${id}`)
  }
}
