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
 *
 * A volume's **name** is its key inside a project: names are unique per project, and
 * every method here accepts either a name or the generated id wherever a volume is
 * addressed. Prefer the name — it is the thing you chose and can reconstruct, while
 * the id only exists after the first create.
 *
 * Names are slugs: lowercase letters, digits and dashes, starting and ending with a
 * letter or digit, up to 64 characters.
 *
 * Mount one to a sandbox via `Sandbox.create({ volumeName: 'my-data' })`.
 */
export class Volume {
  /** The volume's generated id. Stable, but you rarely need it — address by name. */
  readonly volumeId: string
  /** The volume's name: unique within its project, and usable anywhere `volumeId` is. */
  readonly name?: string
  private readonly config: ConnectionConfig

  constructor(opts: { volumeId: string; name?: string } & ConnectionOpts) {
    this.volumeId = opts.volumeId
    this.name = opts.name
    this.config = new ConnectionConfig(opts)
  }

  /**
   * Create a volume. Throws `ConflictError` (409) if the project already has one with
   * this name — use {@link getOrCreate} when you want "make sure this exists" instead.
   */
  static async create(projectId: string, name: string, opts?: CreateVolumeOpts): Promise<Volume> {
    const config = new ConnectionConfig(opts)
    const res = await fetch(`${config.apiUrl}/api/projects/${projectId}/volumes`, {
      method: 'POST',
      headers: config.headers,
      body: JSON.stringify({ name, sizeGb: opts?.sizeGb ?? 5 }),
    })
    if (!res.ok) await handleApiError(res)
    const vol = await res.json() as VolumeInfo
    return new Volume({ volumeId: vol.id, name: vol.name, ...opts })
  }

  /**
   * Return the project's volume with this name, creating it first if it does not
   * exist yet. This is the reason a volume's name is its key: an agent that wants
   * "the scratch disk for this task" no longer has to store an id between runs.
   *
   * An existing volume is returned as-is — `sizeGb` applies only to a fresh create
   * and never resizes one that is already there.
   */
  static async getOrCreate(projectId: string, name: string, opts?: CreateVolumeOpts): Promise<Volume> {
    const config = new ConnectionConfig(opts)
    const res = await fetch(`${config.apiUrl}/api/projects/${projectId}/volumes`, {
      method: 'POST',
      headers: config.headers,
      body: JSON.stringify({ name, sizeGb: opts?.sizeGb ?? 5, getOrCreate: true }),
    })
    if (!res.ok) await handleApiError(res)
    const vol = await res.json() as VolumeInfo
    return new Volume({ volumeId: vol.id, name: vol.name, ...opts })
  }

  /** Look a volume up by name or by id. */
  static async get(projectId: string, nameOrId: string, opts?: ConnectionOpts): Promise<Volume> {
    const config = new ConnectionConfig(opts)
    const res = await fetch(`${config.apiUrl}/api/projects/${projectId}/volumes/${encodeURIComponent(nameOrId)}`, {
      headers: config.headers,
    })
    if (!res.ok) await handleApiError(res)
    const vol = await res.json() as VolumeInfo
    return new Volume({ volumeId: vol.id, name: vol.name, ...opts })
  }

  static async list(projectId: string, opts?: ConnectionOpts): Promise<VolumeInfo[]> {
    const config = new ConnectionConfig(opts)
    const res = await fetch(`${config.apiUrl}/api/projects/${projectId}/volumes`, {
      headers: config.headers,
    })
    if (!res.ok) await handleApiError(res)
    return res.json() as Promise<VolumeInfo[]>
  }

  /** Delete a volume by name or by id, without constructing one first. */
  static async delete(projectId: string, nameOrId: string, opts?: ConnectionOpts): Promise<void> {
    const config = new ConnectionConfig(opts)
    const res = await fetch(`${config.apiUrl}/api/projects/${projectId}/volumes/${encodeURIComponent(nameOrId)}`, {
      method: 'DELETE',
      headers: config.headers,
    })
    if (!res.ok) await handleApiError(res)
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
