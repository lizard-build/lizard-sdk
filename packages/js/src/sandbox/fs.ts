import { ConnectionConfig } from '../config'
import { handleApiError } from '../errors'

export interface FsOpts {
  user?: string
}

export interface FileInfo {
  name: string
  path: string
  type: 'file' | 'dir'
  size: number
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

  private async execInternal(cmd: string, user?: string): Promise<void> {
    const res = await fetch(`${this.config.apiUrl}/api/sandboxes/${this.sandboxId}/exec`, {
      method: 'POST',
      headers: this.config.headers,
      body: JSON.stringify({ cmd, user }),
    })
    if (!res.ok) await handleApiError(res)
  }
}
