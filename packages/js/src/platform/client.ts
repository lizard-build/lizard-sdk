import { ConnectionConfig, type ConnectionOpts } from '../config'
import { handleApiError } from '../errors'

/** Shared HTTP helper for platform (non-sandbox) API calls. */
export class PlatformClient {
  readonly config: ConnectionConfig

  constructor(opts: ConnectionOpts) {
    this.config = new ConnectionConfig(opts)
  }

  async get<T>(path: string): Promise<T> {
    const res = await fetch(`${this.config.apiUrl}${path}`, {
      headers: this.config.headers,
    })
    if (!res.ok) await handleApiError(res)
    return res.json() as Promise<T>
  }

  async post<T>(path: string, body?: unknown): Promise<T> {
    const res = await fetch(`${this.config.apiUrl}${path}`, {
      method: 'POST',
      headers: this.config.headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
    if (!res.ok) await handleApiError(res)
    return res.json() as Promise<T>
  }

  async patch<T>(path: string, body: unknown): Promise<T> {
    const res = await fetch(`${this.config.apiUrl}${path}`, {
      method: 'PATCH',
      headers: this.config.headers,
      body: JSON.stringify(body),
    })
    if (!res.ok) await handleApiError(res)
    return res.json() as Promise<T>
  }

  async delete<T = void>(path: string, body?: unknown): Promise<T> {
    const res = await fetch(`${this.config.apiUrl}${path}`, {
      method: 'DELETE',
      headers: this.config.headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
    if (!res.ok) await handleApiError(res)
    if (res.status === 204 || res.headers.get('content-length') === '0') return undefined as T
    return res.json() as Promise<T>
  }

  async postForm<T>(path: string, form: FormData): Promise<T> {
    const headers = { 'X-API-Key': this.config.apiKey }
    const res = await fetch(`${this.config.apiUrl}${path}`, {
      method: 'POST',
      headers,
      body: form,
    })
    if (!res.ok) await handleApiError(res)
    return res.json() as Promise<T>
  }

  /** Stream SSE events from a path, calling handler for each data line. */
  async *streamSse(path: string): AsyncGenerator<string> {
    const res = await fetch(`${this.config.apiUrl}${path}`, {
      headers: this.config.headers,
    })
    if (!res.ok) await handleApiError(res)
    if (!res.body) return

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const events = buf.split('\n\n')
      buf = events.pop()!
      for (const evt of events) {
        const dataLine = evt.split('\n').find(l => l.startsWith('data: '))
        if (dataLine) yield dataLine.slice(6)
      }
    }
  }
}
