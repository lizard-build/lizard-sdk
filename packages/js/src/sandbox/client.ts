import { ConnectionConfig, ConnectionOpts } from '../config'
import { handleApiError } from '../errors'
import { requireProjectRef, resolveProjectId } from '../project'

export interface SandboxInfo {
  sandboxId: string
  template: string
  startedAt: string
  endAt: string
  /** Region the sandbox runs in — the volume's region when one is attached. */
  region?: string
  status?: string
  cpus?: number
  memoryMb?: number
  metadata?: Record<string, string>
}

export interface SandboxOpts extends ConnectionOpts {
  /**
   * The project this sandbox belongs to — its ID, slug, or name. Required:
   * a sandbox must be attributed to a project so its CPU, RAM, egress, and
   * storage are billed. Prefer the {@link Lizard} client, which pins a project
   * for you. Ignored when {@link SandboxOpts.projectId} is set.
   */
  project?: string
  /** Exact project ID — skips resolving {@link SandboxOpts.project}. */
  projectId?: string
  template?: string
  metadata?: Record<string, string>
  envs?: Record<string, string>
  timeoutMs?: number
  /**
   * Region to run the sandbox in, e.g. `'us-east-1'`.
   *
   * Leave it unset when attaching a volume: a volume is node-local, so the server
   * places the sandbox in the volume's own region. Setting it to a region the volume
   * is not in is rejected with a 400 rather than silently moved — that combination
   * cannot be satisfied.
   *
   * Defaults to the platform's default sandbox region.
   */
  region?: string
  /** Attach a persistent volume by id, mounted at `/data`. */
  volumeId?: string
  /**
   * Attach a persistent volume by name, mounted at `/data`. A volume's name is its
   * key inside a project, so this is usually what you want — see {@link Volume}.
   * Requires the sandbox's project to be given as an exact `projectId`.
   */
  volumeName?: string
  /**
   * A `liz_` API key to write into the sandbox, so `lizard` works inside it. The CLI is
   * preinstalled in every template; this is what authenticates it.
   *
   * The key must belong to the caller — the server verifies that and silently skips the
   * injection otherwise.
   *
   * SECURITY: anything running in the sandbox can read this key, and sandboxes run
   * untrusted code. Pass a WORKSPACE-SCOPED key rather than a full-access one. Scopes are
   * enforced end to end, so a scoped key that escapes is bounded to that one workspace.
   *
   * @example
   * ```ts
   * const sandbox = await Sandbox.create('codex', {
   *   projectId: 'proj_123',
   *   lizardToken: process.env.LIZARD_WORKSPACE_KEY, // scoped to one workspace
   * })
   * await sandbox.process.exec('lizard volume list')
   * ```
   */
  lizardToken?: string
}

/**
 * Low-level HTTP client for the Lizard sandbox API.
 * Extended by the `Sandbox` class — you typically don't use this directly.
 */
export class SandboxClient {
  protected static async createSandbox(
    template: string,
    timeoutMs: number,
    opts?: SandboxOpts
  ): Promise<{ sandboxId: string }> {
    // A sandbox must belong to a project — billing is metered per project. The
    // API rejects project-less creates with 400 PROJECT_REQUIRED; checking here
    // first reports the missing project before the missing API key.
    const ref = requireProjectRef(opts)
    const config = new ConnectionConfig(opts)
    const projectId = ref.projectId ?? (await resolveProjectId(ref.project!, config))
    const res = await fetch(`${config.apiUrl}/api/sandboxes`, {
      method: 'POST',
      headers: config.headers,
      body: JSON.stringify({
        template,
        timeoutMs,
        projectId,
        metadata: opts?.metadata,
        envs: opts?.envs,
        region: opts?.region,
        volumeId: opts?.volumeId,
        volumeName: opts?.volumeName,
        lizardToken: opts?.lizardToken,
      }),
    })
    if (!res.ok) await handleApiError(res)
    return res.json() as Promise<{ sandboxId: string }>
  }

  protected static async killSandbox(sandboxId: string, opts?: ConnectionOpts): Promise<boolean> {
    const config = new ConnectionConfig(opts)
    const res = await fetch(`${config.apiUrl}/api/sandboxes/${sandboxId}`, {
      method: 'DELETE',
      headers: config.headers,
    })
    if (res.status === 404) return false
    if (!res.ok) await handleApiError(res)
    return true
  }

  protected static async pauseSandbox(sandboxId: string, opts?: ConnectionOpts): Promise<boolean> {
    const config = new ConnectionConfig(opts)
    const res = await fetch(`${config.apiUrl}/api/sandboxes/${sandboxId}/pause`, {
      method: 'POST',
      headers: config.headers,
    })
    if (res.status === 404) return false
    if (!res.ok) await handleApiError(res)
    return true
  }

  protected static async resumeSandbox(sandboxId: string, opts?: ConnectionOpts): Promise<boolean> {
    const config = new ConnectionConfig(opts)
    const res = await fetch(`${config.apiUrl}/api/sandboxes/${sandboxId}/resume`, {
      method: 'POST',
      headers: config.headers,
    })
    if (res.status === 404) return false
    if (!res.ok) await handleApiError(res)
    return true
  }

  protected static async listSandboxes(opts?: ConnectionOpts): Promise<SandboxInfo[]> {
    const config = new ConnectionConfig(opts)
    const res = await fetch(`${config.apiUrl}/api/sandboxes`, {
      headers: config.headers,
    })
    if (!res.ok) await handleApiError(res)
    return res.json() as Promise<SandboxInfo[]>
  }

  protected static async getSandboxInfo(sandboxId: string, opts?: ConnectionOpts): Promise<SandboxInfo> {
    const config = new ConnectionConfig(opts)
    const res = await fetch(`${config.apiUrl}/api/sandboxes/${sandboxId}`, {
      headers: config.headers,
    })
    if (!res.ok) await handleApiError(res)
    return res.json() as Promise<SandboxInfo>
  }

  protected static async setTimeoutSandbox(sandboxId: string, timeoutMs: number, opts?: ConnectionOpts): Promise<void> {
    const config = new ConnectionConfig(opts)
    const res = await fetch(`${config.apiUrl}/api/sandboxes/${sandboxId}/timeout`, {
      method: 'POST',
      headers: config.headers,
      body: JSON.stringify({ timeoutMs }),
    })
    if (!res.ok) await handleApiError(res)
  }

  protected static async exposeSandboxPort(
    sandboxId: string,
    port: number,
    opts?: ConnectionOpts
  ): Promise<{ hostname: string; url: string }> {
    const config = new ConnectionConfig(opts)
    const res = await fetch(`${config.apiUrl}/api/sandboxes/${sandboxId}/expose/${port}`, {
      method: 'POST',
      headers: config.headers,
    })
    if (!res.ok) await handleApiError(res)
    return res.json() as Promise<{ hostname: string; url: string }>
  }
}
