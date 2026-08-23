import type { PlatformClient } from './client'
import { LizardError, TimeoutError } from '../errors'

export interface Service {
  id: string
  name: string
  projectId: string
  status: 'none' | 'running' | 'crashed' | 'stopped'
  deployStatus: 'idle' | 'building' | 'deploying' | 'restarting' | 'failed' | 'deleting'
  domain?: string
  region?: string
  sourceType?: 'github' | 'upload'
  repoUrl?: string
  branch?: string
  startCommand?: string
  buildCommand?: string
  containerPort?: number
}

export interface CreateServiceOpts {
  projectId: string
  name: string
  sourceType?: 'github' | 'upload'
  repoUrl?: string
  branch?: string
  startCommand?: string
  buildCommand?: string
  containerPort?: number
  region?: string
  /** Set to 0 for worker mode (no HTTP listener). */
  port?: number
}

export interface ScaleOpts {
  replicas?: number
  cpuMillis?: number
  memoryMi?: number
  storageMi?: number
}

export interface LogLine {
  level: 'info' | 'error' | 'warn' | 'debug'
  message: string
  ts: number
  service?: string
  replica?: string
}

export interface DeployEvent {
  event: 'log' | 'done' | 'error' | 'deployed' | 'failed' | 'deploying'
  line?: string
  message?: string
  status?: string
  url?: string | null
}

/**
 * Handle for a running deploy — stream its logs or await completion.
 *
 * @example
 * ```ts
 * const deploy = await lizard.services.upload({ projectId, source: fs.readFileSync('app.tar.gz') })
 * for await (const line of deploy.logs()) console.log(line)
 * const result = await deploy.wait()
 * console.log('deployed to', result.url)
 * ```
 */
export class DeployHandle {
  private readonly _serviceId: string
  private readonly _buildId: string | undefined
  private readonly _client: PlatformClient

  constructor(client: PlatformClient, serviceId: string, buildId?: string) {
    this._client = client
    this._serviceId = serviceId
    this._buildId = buildId
  }

  get serviceId(): string { return this._serviceId }

  /** Stream build + runtime log lines until the deploy finishes. */
  async *logs(): AsyncGenerator<string> {
    const path = `/api/apps/${this._serviceId}/logs?limit=1000`
    const res = await fetch(`${this._client.config.apiUrl}${path}`, {
      headers: this._client.config.headers,
    })
    if (!res.ok) return
    const body = await res.json() as { logs?: string[] } | string[]
    const lines = Array.isArray(body) ? body : (body.logs ?? [])
    for (const l of lines) yield typeof l === 'string' ? l : JSON.stringify(l)
  }

  /**
   * Poll until the deploy reaches a terminal state.
   * @returns `{ url, status }` on success; throws `LizardError` on failure.
   */
  async wait(opts?: { timeoutMs?: number; pollMs?: number }): Promise<{ url: string | null; status: string }> {
    const deadline = Date.now() + (opts?.timeoutMs ?? 10 * 60_000)
    const pollMs = opts?.pollMs ?? 3000
    while (Date.now() < deadline) {
      const svc = await this._client.get<Service>(`/api/apps/${this._serviceId}`)
      if (svc.deployStatus === 'idle') {
        if (svc.status === 'running') return { url: svc.domain ? `https://${svc.domain}` : null, status: 'running' }
        if (svc.status === 'crashed') throw new LizardError(`Service crashed after deploy`)
      }
      if (svc.deployStatus === 'failed') throw new LizardError(`Deploy failed`)
      await new Promise(r => setTimeout(r, pollMs))
    }
    throw new TimeoutError(`Deploy did not complete within ${opts?.timeoutMs ?? 600_000}ms`)
  }
}

export class ServicesAPI {
  constructor(private readonly client: PlatformClient) {}

  /** List all services in a project. */
  list(opts: { projectId: string }): Promise<Service[]> {
    return this.client.get(`/api/projects/${opts.projectId}/apps`)
  }

  /** Get a service by ID. */
  get(id: string): Promise<Service> {
    return this.client.get(`/api/apps/${id}`)
  }

  /**
   * Create a service and start a deploy from a git repo.
   * Returns a DeployHandle to track progress.
   */
  async deploy(opts: CreateServiceOpts & { waitForDeploy?: boolean }): Promise<DeployHandle> {
    const body: Record<string, unknown> = {
      name: opts.name,
      sourceType: opts.sourceType ?? 'github',
      repoUrl: opts.repoUrl,
      branch: opts.branch ?? 'main',
      startCommand: opts.startCommand,
      buildCommand: opts.buildCommand,
      containerPort: opts.port ?? opts.containerPort,
      region: opts.region,
    }
    const svc = await this.client.post<Service>(`/api/projects/${opts.projectId}/apps`, body)
    return new DeployHandle(this.client, svc.id)
  }

  /**
   * Upload a tarball and deploy it.
   *
   * @param opts.source - A `Buffer`, `Blob`, or `Uint8Array` of a `.tar.gz` file.
   */
  async upload(opts: {
    projectId: string
    name: string
    source: Blob | string
    startCommand?: string
    buildCommand?: string
    port?: number
    region?: string
  }): Promise<DeployHandle> {
    const form = new FormData()
    const blob = opts.source instanceof Blob
      ? opts.source
      : new Blob([opts.source as string], { type: 'application/gzip' })
    form.append('file', blob, 'source.tar.gz')
    form.append('name', opts.name)
    if (opts.startCommand) form.append('startCommand', opts.startCommand)
    if (opts.buildCommand) form.append('buildCommand', opts.buildCommand)
    if (opts.port !== undefined) form.append('containerPort', String(opts.port))
    if (opts.region) form.append('region', opts.region)

    const result = await this.client.postForm<{ id: string; buildId?: string }>(
      `/api/projects/${opts.projectId}/apps/upload`,
      form,
    )
    return new DeployHandle(this.client, result.id, result.buildId)
  }

  /** Trigger a redeploy (rebuild from current source). */
  async redeploy(id: string): Promise<DeployHandle> {
    await this.client.post(`/api/apps/${id}/redeploy`, {})
    return new DeployHandle(this.client, id)
  }

  /** Restart a service without rebuilding. */
  restart(id: string): Promise<void> {
    return this.client.post(`/api/apps/${id}/restart`, {})
  }

  /** Scale a service. */
  scale(id: string, opts: ScaleOpts): Promise<void> {
    return this.client.post(`/api/apps/${id}/scale`, opts)
  }

  /**
   * Get recent log lines. For a live tail, use the WebSocket API instead.
   *
   * @param opts.limit - Max lines to return (default 200, max 1000).
   */
  async logs(id: string, opts?: { limit?: number; since?: string }): Promise<LogLine[]> {
    const qs = new URLSearchParams()
    if (opts?.limit) qs.set('limit', String(opts.limit))
    if (opts?.since) qs.set('since', opts.since)
    const result = await this.client.get<{ logs: LogLine[] } | LogLine[]>(`/api/apps/${id}/logs?${qs}`)
    return Array.isArray(result) ? result : (result.logs ?? [])
  }

  /** Execute a command inside the running service container. */
  exec(id: string, cmd: string, opts?: { timeoutMs?: number }): Promise<{ stdout: string; stderr: string; exitCode: number }> {
    return this.client.post(`/api/apps/${id}/exec`, { cmd, timeoutMs: opts?.timeoutMs })
  }

  /** Update service configuration. */
  update(id: string, opts: Partial<Pick<Service, 'name' | 'startCommand' | 'buildCommand' | 'containerPort' | 'repoUrl' | 'branch' | 'sourceType'>>): Promise<Service> {
    return this.client.patch(`/api/apps/${id}`, opts)
  }

  /** Delete a service. */
  delete(id: string): Promise<void> {
    return this.client.delete(`/api/apps/${id}`)
  }
}
