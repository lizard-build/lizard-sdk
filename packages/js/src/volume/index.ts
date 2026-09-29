import { ConnectionConfig, ConnectionOpts } from '../config'
import { handleApiError } from '../errors'

export interface VolumeInfo {
  id: string
  projectId: string
  name: string
  sizeGb: number
  sizeMb?: number
  /** Region the volume's node lives in. A sandbox mounting it runs here too. */
  region?: string
  status: string
  attachedTo?: string | null
  createdAt: number
  /**
   * Whether `sizeGb` is actually enforced as a hard limit on the volume's node.
   * Returned by {@link Volume.resize}; `false` means the size was recorded but the
   * node cannot enforce it, so writes past it are not refused.
   */
  sizeEnforced?: boolean
}

export interface CreateVolumeOpts extends ConnectionOpts {
  /** Whole GB, default 5. New volumes allow 1–50 GB unless the server config sets another maximum. Creating never changes an existing volume's size; use `Volume.resize` for that. */
  sizeGb?: number
  /**
   * Region to place the volume in, e.g. `'us-east-1'`. A volume is node-local, so
   * this also fixes where any sandbox mounting it must run — `Sandbox.create` takes
   * the volume's region automatically when you don't name one, so you normally set
   * the region here or nowhere.
   *
   * Defaults to the platform's default region.
   */
  region?: string
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
      body: JSON.stringify({ name, sizeGb: opts?.sizeGb ?? 5, region: opts?.region }),
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
   * An existing volume is returned as-is — `sizeGb` applies only to a fresh create,
   * so an existing volume keeps its size. Call {@link Volume.resize} to change it.
   */
  static async getOrCreate(projectId: string, name: string, opts?: CreateVolumeOpts): Promise<Volume> {
    const config = new ConnectionConfig(opts)
    const res = await fetch(`${config.apiUrl}/api/projects/${projectId}/volumes`, {
      method: 'POST',
      headers: config.headers,
      body: JSON.stringify({ name, sizeGb: opts?.sizeGb ?? 5, region: opts?.region, getOrCreate: true }),
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

  /**
   * Resize a volume, by name or by id, to `sizeGb`.
   *
   * The change is in place and online: the size is a quota, so no data is copied,
   * it completes in well under a second, and a sandbox that has the volume mounted
   * keeps running and sees the new size immediately. Both growing and shrinking are
   * allowed, but a shrink must leave at least 10% of the new size free — otherwise
   * it throws `ConflictError` with `code: 'volume_too_full_to_shrink'`.
   *
   * Other failures carry a `code` too: `invalid_volume_size`, `volume_not_resizable`,
   * `volume_resize_in_progress`, `volume_not_provisioned`,
   * `volume_capacity_unavailable`, and `volume_resize_timeout` (a `TimeoutError`;
   * the size is left unchanged).
   *
   * @returns The volume's updated info, including `sizeEnforced`.
   */
  static async resize(projectId: string, nameOrId: string, sizeGb: number, opts?: ConnectionOpts): Promise<VolumeInfo> {
    const config = new ConnectionConfig(opts)
    const res = await fetch(`${config.apiUrl}/api/projects/${projectId}/volumes/${encodeURIComponent(nameOrId)}`, {
      method: 'PATCH',
      headers: config.headers,
      body: JSON.stringify({ sizeGb }),
    })
    if (!res.ok) await handleApiError(res)
    return res.json() as Promise<VolumeInfo>
  }

  async getInfo(projectId: string): Promise<VolumeInfo> {
    const res = await fetch(`${this.config.apiUrl}/api/projects/${projectId}/volumes/${this.volumeId}`, {
      headers: this.config.headers,
    })
    if (!res.ok) await handleApiError(res)
    return res.json() as Promise<VolumeInfo>
  }

  /** Resize this volume in place — see the static {@link Volume.resize}. */
  async resize(projectId: string, sizeGb: number): Promise<VolumeInfo> {
    return Volume.resize(projectId, this.volumeId, sizeGb, {
      apiKey: this.config.apiKey,
      apiUrl: this.config.apiUrl,
    })
  }

  async delete(projectId: string): Promise<void> {
    const res = await fetch(`${this.config.apiUrl}/api/projects/${projectId}/volumes/${this.volumeId}`, {
      method: 'DELETE',
      headers: this.config.headers,
    })
    if (!res.ok) await handleApiError(res)
  }
}
