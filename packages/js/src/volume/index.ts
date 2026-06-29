import { ConnectionConfig, ConnectionOpts } from '../config'
import { handleApiError } from '../errors'

export interface VolumeInfo {
  id: string
  projectId: string
  name: string
  sizeGb: number
  sizeMb?: number
  status: string
  attachedTo?: string | null
  createdAt: number
}

export interface CreateVolumeOpts extends ConnectionOpts {
  sizeGb?: number
}

/**
 * A persistent volume that outlives sandboxes.
 * Mount it to a sandbox via `Sandbox.create({ volumeId: volume.volumeId })`.
 */
export class Volume {
  readonly volumeId: string
  private readonly config: ConnectionConfig

  constructor(opts: { volumeId: string } & ConnectionOpts) {
    this.volumeId = opts.volumeId
    this.config = new ConnectionConfig(opts)
  }

  static async create(projectId: string, name: string, opts?: CreateVolumeOpts): Promise<Volume> {
    const config = new ConnectionConfig(opts)
    const res = await fetch(`${config.apiUrl}/api/projects/${projectId}/volumes`, {
      method: 'POST',
      headers: config.headers,
      body: JSON.stringify({ name, sizeGb: opts?.sizeGb ?? 5 }),
    })
    if (!res.ok) await handleApiError(res)
    const vol = await res.json() as VolumeInfo
    return new Volume({ volumeId: vol.id, ...opts })
  }

  static async get(projectId: string, volumeId: string, opts?: ConnectionOpts): Promise<Volume> {
    const config = new ConnectionConfig(opts)
    const res = await fetch(`${config.apiUrl}/api/projects/${projectId}/volumes/${volumeId}`, {
      headers: config.headers,
    })
    if (!res.ok) await handleApiError(res)
    return new Volume({ volumeId, ...opts })
  }

  static async list(projectId: string, opts?: ConnectionOpts): Promise<VolumeInfo[]> {
    const config = new ConnectionConfig(opts)
    const res = await fetch(`${config.apiUrl}/api/projects/${projectId}/volumes`, {
      headers: config.headers,
    })
    if (!res.ok) await handleApiError(res)
    return res.json() as Promise<VolumeInfo[]>
  }

  async getInfo(projectId: string): Promise<VolumeInfo> {
    const res = await fetch(`${this.config.apiUrl}/api/projects/${projectId}/volumes/${this.volumeId}`, {
      headers: this.config.headers,
    })
    if (!res.ok) await handleApiError(res)
    return res.json() as Promise<VolumeInfo>
  }

  async delete(projectId: string): Promise<void> {
    const res = await fetch(`${this.config.apiUrl}/api/projects/${projectId}/volumes/${this.volumeId}`, {
      method: 'DELETE',
      headers: this.config.headers,
    })
    if (!res.ok) await handleApiError(res)
  }
}
