import { ConnectionConfig, ConnectionOpts } from '../config'
import { handleApiError } from '../errors'

export interface SandboxInfo {
  sandboxId: string
  template: string
  startedAt: string
  endAt: string
  metadata?: Record<string, string>
}

export interface SandboxOpts extends ConnectionOpts {
  template?: string
  metadata?: Record<string, string>
  envs?: Record<string, string>
  timeoutMs?: number
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
    const config = new ConnectionConfig(opts)
    const res = await fetch(`${config.apiUrl}/api/sandboxes`, {
      method: 'POST',
      headers: config.headers,
      body: JSON.stringify({
        template,
        timeoutMs,
        metadata: opts?.metadata,
        envs: opts?.envs,
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
