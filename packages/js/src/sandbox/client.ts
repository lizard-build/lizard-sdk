import { ConnectionConfig, ConnectionOpts } from '../config'
import { handleApiError } from '../errors'
import { requireProjectRef, resolveProjectId } from '../project'

export interface SandboxInfo {
  sandboxId: string
  template: string
  startedAt: string
  endAt: string
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
  volumeId?: string
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
        volumeId: opts?.volumeId,
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
