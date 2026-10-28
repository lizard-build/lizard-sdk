import { ConnectionConfig, ConnectionOpts, DEFAULT_SANDBOX_REGION } from '../config'
import { LizardError, handleApiError } from '../errors'
import { requireProjectRef, resolveProjectId } from '../project'

export interface SandboxInfo {
  sandboxId: string
  template: string
  startedAt: string
  endAt: string
  /** Region the sandbox runs in — the volume's region when one is attached. */
  region?: string
  status?: string
  /** The sandbox runtime: `'firecracker'` (a microVM), or `null` when unknown. */
  runtime?: 'firecracker' | 'container' | null
  pauseError?: string | null
  /** Machine size (`'small' | 'medium' | 'large'`); may be `null` for a sandbox billed by measured usage. */
  size?: 'small' | 'medium' | 'large' | null
  /** Flat hourly price in USD for `size`, billed per second while running; may be `null` when billed by measured usage. */
  pricePerHour?: number | null
  /** `false` when the sandbox was created with `internetAccess: false`; absent from older servers. */
  internetAccess?: boolean
  cpus?: number
  memoryMb?: number
  metadata?: Record<string, string>
}

/** A sandbox port published on a public HTTPS hostname. See {@link Sandbox.exposePort}. */
export interface ExposedPort {
  /** Hostname without a scheme, e.g. `abc-3000.sandbox.eu-west-lim-a.onlizard.com`. */
  hostname: string
  /** A browser URL that carries the access token (`?lizard_token=...`). */
  url: string
  port: number
  /**
   * The port is private: every request needs this token, either as the
   * `X-Lizard-Access-Token` header or once as `?lizard_token=` (a browser then gets a cookie).
   */
  accessToken: string
}

export interface SandboxOpts extends ConnectionOpts {
  /**
   * The project this sandbox belongs to — its ID, slug, or name. Required:
   * a sandbox must be attributed to a project so its usage is billed there —
   * a flat hourly price per {@link SandboxOpts.size}, charged per second while
   * it runs (attached volumes bill separately). Prefer the {@link Lizard} client, which pins a project
   * for you. Ignored when {@link SandboxOpts.projectId} is set.
   */
  project?: string
  /** Exact project ID — skips resolving {@link SandboxOpts.project}. */
  projectId?: string
  template?: string
  /**
   * Create from a private saved snapshot. The sandbox runs at the source sandbox's
   * size and is billed flat at that size; `size` is ignored.
   */
  snapshotId?: string
  /**
   * Machine size, billed flat per hour (per second of running time):
   * - `'small'`  — 2 vCPU / 4 GB, $0.0162/h
   * - `'medium'` — 4 vCPU / 8 GB, $0.0324/h (default)
   * - `'large'`  — 8 vCPU / 16 GB, $0.0648/h
   *
   * On the Pro trial only `'small'` (also the default there) in a US region starts; another
   * size or region throws `AuthenticationError` (HTTP 403, `TRIAL_SANDBOX_SIZE` /
   * `TRIAL_SANDBOX_REGION`) until the first Pro payment.
   *
   * CPU/RAM are included; running time includes idle time. Sandbox egress includes 2 TB per
   * account over a rolling 30 days: https://lizard.build/docs/platform/limits/#sandbox-egress
   * A successful pause stops compute charges; Persistent Volumes storage bills separately.
   * Ignored with {@link SandboxOpts.snapshotId}.
   */
  size?: 'small' | 'medium' | 'large'
  /** Your own key/value labels for the sandbox, returned by `getInfo()` and `list()`. */
  metadata?: Record<string, string>
  /** Environment variables set in the sandbox, visible to every command it runs. */
  envs?: Record<string, string>
  /**
   * `false`: no internet for the sandbox's whole life, its resumes and forks included (no
   * outbound TCP, UDP, DNS or ping) and no public ports (`exposePort` is refused); commands
   * and files still work. Set at
   * create only. Default `true`. Not available with a container volume or snapshot.
   */
  internetAccess?: boolean
  timeoutMs?: number
  /**
   * Region to run the sandbox in, e.g. `'us-east-1'`.
   *
   * Leave it unset when attaching a volume: a volume is node-local, so the server
   * places the sandbox in the volume's own region. Setting it to a region the volume
   * is not in is rejected with a 400 rather than silently moved — that combination
   * cannot be satisfied.
   *
   * Defaults to `'us-east-1'`, or to the volume's or snapshot's region when one is given.
   */
  region?: string
  /** Attach a persistent volume by id, mounted at `/workspace`. */
  volumeId?: string
  /**
   * Attach a persistent volume by name, mounted at `/workspace`. A volume's name is its
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

/** The platform's answer for a region that takes no new sandboxes for now. Reads a clone. */
async function regionUnavailable(res: Response): Promise<boolean> {
  try {
    const body = await res.clone().json() as { code?: unknown }
    return body?.code === 'region_unavailable'
  } catch {
    return false
  }
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
    // No region: us-east-1. A volume or a snapshot exists in one region only, so with either
    // the server places the sandbox there instead.
    const defaultRegion = !opts?.region && !opts?.volumeId && !opts?.volumeName && !opts?.snapshotId
    const post = (region: string | undefined) => fetch(`${config.apiUrl}/api/sandboxes`, {
      method: 'POST',
      headers: config.headers,
      body: JSON.stringify({
        template,
        snapshotId: opts?.snapshotId,
        size: opts?.size,
        timeoutMs,
        projectId,
        metadata: opts?.metadata,
        envs: opts?.envs,
        region,
        volumeId: opts?.volumeId,
        volumeName: opts?.volumeName,
        lizardToken: opts?.lizardToken,
        // Sent only when asked: every other create stays what it was.
        ...(opts?.internetAccess === false ? { internetAccess: false } : {}),
      }),
    })
    let res = await post(opts?.region || (defaultRegion ? DEFAULT_SANDBOX_REGION : undefined))
    // New sandboxes paused in the default region: ask again without one, and the platform
    // picks an open region. A region the caller named is never swapped for another.
    if (defaultRegion && res.status === 503 && (await regionUnavailable(res))) res = await post(undefined)
    if (!res.ok) await handleApiError(res)
    const created = (await res.json()) as { sandboxId: string; internetAccess?: boolean }
    // A server that predates the option ignores it and starts a sandbox WITH internet: asked
    // for none, anything but an explicit false is deleted, never handed over.
    if (opts?.internetAccess === false && created.internetAccess !== false) {
      await this.killSandbox(created.sandboxId, opts).catch(() => {})
      throw new LizardError("This server does not support internetAccess: false yet; the sandbox it started had internet and was deleted")
    }
    return created
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

  protected static async pauseSandbox(sandboxId: string, opts?: ConnectionOpts & { fast?: boolean; memory?: boolean }): Promise<boolean> {
    const config = new ConnectionConfig(opts)
    const res = await fetch(`${config.apiUrl}/api/sandboxes/${sandboxId}/pause`, {
      method: 'POST',
      // Sent as memory:false, which every server that has fast pause accepts.
      ...(opts?.fast === true || opts?.memory === false
        ? { headers: { ...config.headers, 'Content-Type': 'application/json' }, body: JSON.stringify({ memory: false }) }
        : { headers: config.headers }),
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

  protected static async listSandboxes(opts?: ConnectionOpts & { projectId?: string }): Promise<SandboxInfo[]> {
    const config = new ConnectionConfig(opts)
    const path = opts?.projectId ? `/api/projects/${encodeURIComponent(opts.projectId)}/sandboxes` : '/api/sandboxes'
    const res = await fetch(`${config.apiUrl}${path}`, {
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
  ): Promise<ExposedPort> {
    const config = new ConnectionConfig(opts)
    const res = await fetch(`${config.apiUrl}/api/sandboxes/${sandboxId}/expose/${port}`, {
      method: 'POST',
      headers: config.headers,
    })
    if (!res.ok) await handleApiError(res)
    return res.json() as Promise<ExposedPort>
  }
}
