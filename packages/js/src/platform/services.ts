import { type PlatformClient, query } from './client'
import type { ConfigResult } from './projects'
import { LizardError, TimeoutError } from '../errors'

export interface Service {
  id: string
  name: string
  projectId: string
  status: 'none' | 'running' | 'crashed' | 'stopped'
  deployStatus: 'idle' | 'building' | 'deploying' | 'restarting' | 'failed' | 'deleting'
  domain?: string
  region?: string
  sourceType?: 'github' | 'upload' | 'docker'
  repoUrl?: string
  branch?: string
  startCommand?: string
  buildCommand?: string
  containerPort?: number
}

export interface CreateServiceOpts {
  projectId: string
  name: string
  sourceType?: 'github' | 'upload' | 'docker'
  repoUrl?: string
  branch?: string
  startCommand?: string
  buildCommand?: string
  containerPort?: number
  region?: string
  preDeployCommand?: string
  dockerfilePath?: string
  rootDirectory?: string
  envVars?: Record<string, string>
  skipInitialDeploy?: boolean
  cpuLimit?: string
  memoryLimit?: string
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

  /** Stream build log messages until the server closes the build stream. */
  async *logs(): AsyncGenerator<string> {
    let buildId = this._buildId
    if (!buildId) {
      const svc = await this._client.get<{ builds?: Array<{ id: string }> }>(`/api/apps/${this._serviceId}`)
      buildId = svc.builds?.[0]?.id
    }
    if (!buildId) throw new LizardError('No build found for this deploy')
    for await (const event of this._client.events(`/api/builds/${buildId}/logs`)) {
      if (event.event === 'error') throw new LizardError(event.data)
      if (event.event === 'done') return
      let data: unknown
      try { data = JSON.parse(event.data) } catch { data = event.data }
      yield typeof data === 'string' ? data : event.data
    }
  }

  /**
   * Poll until the deploy reaches a terminal state.
   * @returns `{ url, status }` on success; throws `LizardError` on failure.
   */
  async wait(opts?: { timeoutMs?: number; pollMs?: number }): Promise<{ url: string | null; status: string }> {
    const deadline = Date.now() + (opts?.timeoutMs ?? 10 * 60_000)
    const pollMs = opts?.pollMs ?? 3000
    while (Date.now() < deadline) {
      let buildDone = true
      if (this._buildId) {
        const build = await this._client.get<{ status: string }>(`/api/builds/${this._buildId}`)
        if (build.status === 'failed' || build.status === 'cancelled') throw new LizardError(`Deploy ${build.status}`)
        buildDone = build.status === 'done'
      }
      const svc = await this._client.get<Service>(`/api/apps/${this._serviceId}`)
      if (svc.deployStatus === 'idle') {
        if (buildDone && svc.status === 'running') return { url: svc.domain ? `https://${svc.domain}` : null, status: 'running' }
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
      preDeployCommand: opts.preDeployCommand,
      dockerfilePath: opts.dockerfilePath,
      context: opts.rootDirectory,
      envVars: opts.envVars,
      skipInitialDeploy: opts.skipInitialDeploy,
      cpuLimit: opts.cpuLimit,
      memoryLimit: opts.memoryLimit,
      containerPort: opts.port ?? opts.containerPort,
      region: opts.region,
    }
    const svc = await this.client.post<Service & { buildId?: string }>(`/api/projects/${opts.projectId}/apps`, body)
    const handle = new DeployHandle(this.client, svc.id, svc.buildId)
    if (opts.waitForDeploy) await handle.wait()
    return handle
  }

  /**
   * Upload a tarball and deploy it.
   *
   * @param opts.source - A `Buffer`, `Blob`, or `Uint8Array` of a `.tar.gz` file.
   */
  async upload(opts: {
    projectId: string; name?: string; serviceId?: string; source: Blob | Uint8Array | string
    startCommand?: string; buildCommand?: string; preDeployCommand?: string; port?: number; region?: string
  }): Promise<DeployHandle> {
    if (!opts.name && !opts.serviceId) throw new LizardError('name or serviceId is required')
    const path = query(`/api/projects/${opts.projectId}/apps/upload`, {
      name: opts.name, appId: opts.serviceId, startCommand: opts.startCommand,
      buildCommand: opts.buildCommand, preDeployCommand: opts.preDeployCommand,
      port: opts.port, region: opts.region,
    })
    const result = await this.client.sendBytes<{ id: string; buildId?: string }>('POST', path, opts.source)
    return new DeployHandle(this.client, result.id, result.buildId)
  }

  /** Trigger a redeploy (rebuild from current source). */
  async redeploy(id: string): Promise<DeployHandle> {
    const build = await this.client.post<{ id: string }>(`/api/apps/${id}/redeploy`, {})
    return new DeployHandle(this.client, id, build.id)
  }

  /** Restart a service without rebuilding. */
  restart(id: string): Promise<void> {
    return this.client.post(`/api/apps/${id}/restart`, {})
  }

  /** Scale a service. */
  async scale(id: string, opts: ScaleOpts): Promise<void> {
    if (opts.storageMi !== undefined) throw new LizardError('Storage scaling is only supported for addons')
    if (opts.replicas !== undefined) await this.client.patch(`/api/apps/${id}/scale`, { replicas: opts.replicas })
    if (opts.cpuMillis !== undefined || opts.memoryMi !== undefined) {
      await this.update(id, {
        ...(opts.cpuMillis !== undefined ? { cpuLimit: `${opts.cpuMillis}m` } : {}),
        ...(opts.memoryMi !== undefined ? { memoryLimit: `${opts.memoryMi}Mi` } : {}),
      })
    }
  }

  /**
   * Get recent log lines. For a live tail, use the WebSocket API instead.
   *
   * @param opts.limit - Max lines to return (default 200, max 1000).
   */
  async logs(id: string, opts?: { limit?: number; since?: string }): Promise<LogLine[]> {
    const svc = await this.get(id)
    const result = await this.client.get<{ logs: LogLine[] } | LogLine[]>(query(`/api/projects/${svc.projectId}/logs`, { service: svc.name, limit: opts?.limit ?? 200, since: opts?.since }))
    return Array.isArray(result) ? result : (result.logs ?? [])
  }

  /** Execute a command; collect SSE output and require an exit event. */
  async exec(id: string, cmd: string, opts?: { timeoutMs?: number }): Promise<{ stdout: string; stderr: string; exitCode: number }> {
    const result = { stdout: '', stderr: '', exitCode: -1 }
    for await (const event of this.client.events(`/api/apps/${id}/exec`, {
      method: 'POST', body: { cmd }, signal: AbortSignal.timeout(opts?.timeoutMs ?? 300_000),
    })) {
      if (event.event === 'error') throw new LizardError(event.data)
      const data = JSON.parse(event.data) as { stream?: 'stdout' | 'stderr'; line?: string; exitCode?: number }
      if (data.stream === 'stdout' || data.stream === 'stderr') result[data.stream] += (data.line ?? '') + '\n'
      if (event.event === 'exit' && typeof data.exitCode === 'number') result.exitCode = data.exitCode
    }
    if (result.exitCode === -1) throw new LizardError('Exec stream ended without exit status')
    return result
  }

  async update(id: string, opts: ServiceUpdate, controls: { revision?: number; force?: boolean } = {}): Promise<ConfigResult> {
    const svc = await this.get(id)
    let revision = controls.revision
    if (!controls.force && revision === undefined) {
      const project = await this.client.get<{ configRevision: number }>(`/api/projects/${svc.projectId}`)
      revision = project.configRevision
    }
    return this.client.applyConfig(svc.projectId, {
      ...(controls.force ? {} : { revision }), services: [{ name: svc.name, ...opts, id }],
    })
  }
  events(id: string, buildId?: string): Promise<unknown[]> {
    return this.client.get(query(`/api/apps/${id}/deploy-events`, { buildId }))
  }
  pods(id: string): Promise<{ pods: unknown[] }> { return this.client.get(`/api/apps/${id}/pod-status`) }
  history(id: string, opts: { limit?: number; before?: string; level?: string } = {}): Promise<unknown> {
    return this.client.get(query(`/api/apps/${id}/logs/history`, opts))
  }
  streamLogs(id: string, signal?: AbortSignal) { return this.client.events(`/api/apps/${id}/logs`, { signal }) }
  buildLogs(buildId: string, signal?: AbortSignal) { return this.client.events(`/api/builds/${buildId}/logs`, { signal }) }

  /** Delete a service. */
  delete(id: string): Promise<void> {
    return this.client.delete(`/api/apps/${id}`)
  }
}

export interface ServiceUpdate {
  name?: string; branch?: string; repoUrl?: string; sourceType?: 'github' | 'upload' | 'docker'
  buildCommand?: string | null; startCommand?: string | null; preDeployCommand?: string | null
  dockerfilePath?: string | null; rootDirectory?: string | null; watchPatterns?: string[]
  containerPort?: number; cpuLimit?: string; memoryLimit?: string; desiredReplicas?: number
  context?: string; autoDeploy?: boolean; vpnEnabled?: boolean
}
