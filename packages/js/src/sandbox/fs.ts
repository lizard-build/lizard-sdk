import { ConnectionConfig } from '../config'
import { handleApiError } from '../errors'

export interface FsOpts {
  user?: string
}

/** A filesystem change reported by a {@link Watcher}. */
export interface FsEvent {
  type: 'create' | 'write' | 'remove' | 'rename' | 'chmod'
  /** The entry's name within its directory. */
  name: string
  /** Full path inside the sandbox. */
  path: string
}

export interface FileInfo {
  name: string
  path: string
  type: 'file' | 'dir' | 'symlink'
  size: number
  /** Permission bits as a number, e.g. `0o644` (420). */
  mode?: number
  /** Permission bits as a string, e.g. `-rw-r--r--`. */
  permissions?: string
  /** Owning user name. */
  owner?: string
  /** Owning group name. */
  group?: string
  /** Last modification time, unix milliseconds. */
  modTime?: number
  /** Same as `modTime`, unix milliseconds. */
  modifiedAt?: number
  /** Where a symlink points, for a symlink. */
  symlinkTarget?: string
}

/**
 * Read and write files inside a Lizard sandbox.
 *
 * Access via `sandbox.fs`.
 */
export class Fs {
  constructor(
    private readonly sandboxId: string,
    private readonly config: ConnectionConfig
  ) {}

  /**
   * Write a file into the sandbox filesystem.
   *
   * Creates parent directories automatically if they don't exist. A string is
   * written as UTF-8; bytes (`Uint8Array`, `Buffer` or `ArrayBuffer`) are written
   * exactly as given, so binary files round-trip with {@link readBytes}.
   *
   * With `opts.user` the file is written as (and owned by) that user.
   *
   * @example
   * ```ts
   * await sandbox.fs.write('/app/index.js', 'console.log("hello")')
   * ```
   *
   * @example Write binary data:
   * ```ts
   * await sandbox.fs.write('/app/logo.png', await readFile('logo.png'))
   * ```
   */
  async write(path: string, data: string | Uint8Array | ArrayBuffer, opts?: FsOpts): Promise<void> {
    // Bytes go base64-encoded: a JSON string cannot carry arbitrary binary.
    const body = typeof data === 'string'
      ? { path, content: data, user: opts?.user }
      : { path, content: bytesToBase64(data instanceof ArrayBuffer ? new Uint8Array(data) : data), encoding: 'base64', user: opts?.user }
    const res = await fetch(`${this.config.apiUrl}/api/sandboxes/${this.sandboxId}/files`, {
      method: 'POST',
      headers: this.config.headers,
      body: JSON.stringify(body),
    })
    if (!res.ok) await handleApiError(res)
  }

  /**
   * Read a file from the sandbox filesystem.
   *
   * @returns The file contents as a UTF-8 string. Use {@link readBytes} for binary files.
   *
   * Throws `NotFoundError` if the path does not exist.
   * @example
   * ```ts
   * const content = await sandbox.fs.read('/app/index.js')
   * ```
   */
  async read(path: string, opts?: FsOpts): Promise<string> {
    const url = new URL(`${this.config.apiUrl}/api/sandboxes/${this.sandboxId}/files`)
    url.searchParams.set('path', path)
    if (opts?.user) url.searchParams.set('user', opts.user)

    const res = await fetch(url.toString(), { headers: this.config.headers })
    if (!res.ok) await handleApiError(res)
    return res.text()
  }

  /** Read a file as bytes. */
  async readBytes(path: string, opts?: FsOpts): Promise<Uint8Array> {
    const url = new URL(`${this.config.apiUrl}/api/sandboxes/${this.sandboxId}/files`)
    url.searchParams.set('path', path)
    if (opts?.user) url.searchParams.set('user', opts.user)
    const res = await fetch(url, { headers: this.config.headers })
    if (!res.ok) await handleApiError(res)
    return new Uint8Array(await res.arrayBuffer())
  }

  /**
   * List files and directories at the given path inside the sandbox.
   *
   * @example
   * ```ts
   * const entries = await sandbox.fs.list('/app')
   * ```
   */
  async list(path: string, opts?: FsOpts): Promise<FileInfo[]> {
    const url = new URL(`${this.config.apiUrl}/api/sandboxes/${this.sandboxId}/files/list`)
    url.searchParams.set('path', path)
    if (opts?.user) url.searchParams.set('user', opts.user)

    const res = await fetch(url.toString(), { headers: this.config.headers })
    if (!res.ok) await handleApiError(res)
    return res.json() as Promise<FileInfo[]>
  }

  /**
   * Remove a file or directory from the sandbox filesystem.
   */
  async remove(path: string, opts?: FsOpts): Promise<void> {
    const res = await fetch(`${this.config.apiUrl}/api/sandboxes/${this.sandboxId}/files`, {
      method: 'DELETE',
      headers: this.config.headers,
      body: JSON.stringify({ path, user: opts?.user }),
    })
    if (!res.ok) await handleApiError(res)
  }

  /**
   * Create a directory (and any missing parents) inside the sandbox.
   */
  async makeDir(path: string, opts?: FsOpts): Promise<void> {
    await this.execInternal(`mkdir -p ${JSON.stringify(path)}`, opts?.user)
  }

  /**
   * Metadata for a single path — size, type, permissions, modification time.
   *
   * Saves listing a parent directory and filtering it just to answer "does this
   * exist, and how big is it".
   *
   * @example
   * ```ts
   * const info = await sandbox.fs.stat('/app/out.bin')
   * console.log(info.size, info.type)
   * ```
   *
   * Throws `NotFoundError` if the path does not exist.
   */
  async stat(path: string, opts?: FsOpts): Promise<FileInfo> {
    const url = new URL(`${this.config.apiUrl}/api/sandboxes/${this.sandboxId}/files/stat`)
    url.searchParams.set('path', path)
    if (opts?.user) url.searchParams.set('user', opts.user)

    const res = await fetch(url.toString(), { headers: this.config.headers })
    if (!res.ok) await handleApiError(res)
    return res.json() as Promise<FileInfo>
  }

  /**
   * Move or rename a path. Creates the destination's parent directories.
   *
   * @example
   * ```ts
   * await sandbox.fs.move('/tmp/build.log', '/app/logs/build.log')
   * ```
   */
  async move(from: string, to: string): Promise<void> {
    const res = await fetch(`${this.config.apiUrl}/api/sandboxes/${this.sandboxId}/files/move`, {
      method: 'POST',
      headers: this.config.headers,
      body: JSON.stringify({ from, to }),
    })
    if (!res.ok) await handleApiError(res)
  }

  /**
   * Watch a directory for changes.
   *
   * Polling rather than a push stream: the events cross two proxy hops, and a
   * long-lived stream through both is exactly what breaks first. Call
   * {@link Watcher.getEvents} on whatever interval suits you — each call drains
   * everything queued since the last one, so nothing is missed between polls.
   *
   * Remember to {@link Watcher.close} it; an abandoned watcher keeps queueing
   * events in the guest until the sandbox ends (bounded, but wasted).
   *
   * @example
   * ```ts
   * const w = await sandbox.fs.watch('/app', { recursive: true })
   * setInterval(async () => {
   *   for (const e of await w.getEvents()) console.log(e.type, e.path)
   * }, 1000)
   * ```
   *
   * Not available on Firecracker sandboxes yet: the call throws `LizardError` (501).
   */
  async watch(path: string, opts?: { recursive?: boolean }): Promise<Watcher> {
    const res = await fetch(`${this.config.apiUrl}/api/sandboxes/${this.sandboxId}/files/watch`, {
      method: 'POST',
      headers: this.config.headers,
      body: JSON.stringify({ path, recursive: opts?.recursive ?? false }),
    })
    if (!res.ok) await handleApiError(res)
    const { watcherId } = await res.json() as { watcherId: string }
    return new Watcher(this.sandboxId, this.config, watcherId)
  }

  private async execInternal(cmd: string, user?: string): Promise<void> {
    const res = await fetch(`${this.config.apiUrl}/api/sandboxes/${this.sandboxId}/exec`, {
      method: 'POST',
      headers: this.config.headers,
      body: JSON.stringify({ cmd, user }),
    })
    if (!res.ok) await handleApiError(res)
  }
}

/**
 * A handle to a directory watch inside a sandbox. Created by {@link Fs.watch}.
 */
export class Watcher {
  constructor(
    private readonly sandboxId: string,
    private readonly config: ConnectionConfig,
    /** Server-side id for this watch. */
    readonly watcherId: string
  ) {}

  /**
   * Drain every change since the last call. Returns an empty array when nothing
   * has happened — that is not an error, just a quiet interval.
   */
  async getEvents(): Promise<FsEvent[]> {
    const url = new URL(`${this.config.apiUrl}/api/sandboxes/${this.sandboxId}/files/watch/events`)
    url.searchParams.set('watcherId', this.watcherId)
    const res = await fetch(url.toString(), { headers: this.config.headers })
    if (!res.ok) await handleApiError(res)
    return res.json() as Promise<FsEvent[]>
  }

  /** Stop watching and release the guest-side queue. */
  async close(): Promise<void> {
    const url = new URL(`${this.config.apiUrl}/api/sandboxes/${this.sandboxId}/files/watch`)
    url.searchParams.set('watcherId', this.watcherId)
    const res = await fetch(url.toString(), { method: 'DELETE', headers: this.config.headers })
    if (!res.ok) await handleApiError(res)
  }
}

function bytesToBase64(bytes: Uint8Array): string {
  if (typeof Buffer !== 'undefined') return Buffer.from(bytes.buffer, bytes.byteOffset, bytes.byteLength).toString('base64')
  let s = ''
  for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode(...bytes.subarray(i, i + 0x8000))
  return btoa(s)
}
