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
  /** Permission bits as a string, e.g. `-rw-r--r--`. Absent on older sandboxes. */
  mode?: string
  /** Last modification time, unix milliseconds. Absent on older sandboxes. */
  modTime?: number
}

/**
 * Read and write files inside a Lizard sandbox microVM.
 *
 * Access via `sandbox.fs`.
 */
export class Fs {
  constructor(
    private readonly sandboxId: string,
    private readonly config: ConnectionConfig
  ) {}

  /**
   * Write a file into the microVM filesystem.
   *
   * Creates parent directories automatically if they don't exist.
   *
   * @example
   * ```ts
   * await sandbox.fs.write('/app/index.js', 'console.log("hello")')
   * ```
   *
   * @example Write binary data:
   * ```ts
   * await sandbox.fs.write('/app/data.bin', buffer)
   * ```
   */
  async write(path: string, data: string | Uint8Array, opts?: FsOpts): Promise<void> {
    const content = typeof data === 'string' ? data : new TextDecoder().decode(data)
    const res = await fetch(`${this.config.apiUrl}/api/sandboxes/${this.sandboxId}/files`, {
      method: 'POST',
      headers: this.config.headers,
      body: JSON.stringify({ path, content, user: opts?.user }),
    })
    if (!res.ok) await handleApiError(res)
  }

  /**
   * Read a file from the microVM filesystem.
   *
   * @returns The file contents as a UTF-8 string.
   *
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

  /**
   * List files and directories at the given path inside the microVM.
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
   * Remove a file or directory from the microVM filesystem.
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
   * Create a directory (and any missing parents) inside the microVM.
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
   * Throws `NotFoundError` if the path does not exist. Sandboxes created before
   * this shipped run a guest agent without it and throw `LizardError` (501) —
   * recreate the sandbox to use it.
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
   *
   * Sandboxes created before this shipped run a guest agent without it and throw
   * `LizardError` (501) — recreate the sandbox to use it.
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
   * Sandboxes created before this shipped run a guest agent without it and throw
   * `LizardError` (501) — recreate the sandbox to use it.
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
