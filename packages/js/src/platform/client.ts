import { ConnectionConfig, type ConnectionOpts } from '../config'
import { ConfigApplyError, handleApiError } from '../errors'

export interface StreamEvent { event: string; data: string; id?: string }
export const segment = (value: string): string => encodeURIComponent(value)
export function query(path: string, values: Record<string, string | number | boolean | undefined>): string {
  const qs = new URLSearchParams()
  for (const [key, value] of Object.entries(values)) if (value !== undefined) qs.set(key, String(value))
  return qs.size ? `${path}?${qs}` : path
}

/** HTTP transport. Calls never retry mutations or payments. */
export class PlatformClient {
  readonly config: ConnectionConfig
  constructor(opts: ConnectionOpts) { this.config = new ConnectionConfig(opts) }

  private async json<T>(res: Response): Promise<T> {
    if (!res.ok) await handleApiError(res)
    if (res.status === 204 || res.headers.get('content-length') === '0') return undefined as T
    const text = await res.text()
    return (text ? JSON.parse(text) : undefined) as T
  }
  request<T>(method: string, path: string, body?: unknown): Promise<T> {
    return fetch(`${this.config.apiUrl}${path}`, {
      method, headers: this.config.headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(this.config.requestTimeoutMs),
    }).then(res => this.json<T>(res))
  }
  get<T>(path: string): Promise<T> { return this.request('GET', path) }
  post<T>(path: string, body?: unknown): Promise<T> { return this.request('POST', path, body) }
  put<T>(path: string, body: unknown): Promise<T> { return this.request('PUT', path, body) }
  patch<T>(path: string, body: unknown): Promise<T> { return this.request('PATCH', path, body) }
  delete<T = void>(path: string, body?: unknown): Promise<T> { return this.request('DELETE', path, body) }
  async applyConfig<T>(projectId: string, body: unknown): Promise<T> {
    const result = await this.post<T & { sideEffectFailures?: unknown[] }>(`/api/projects/${projectId}/config:apply`, body)
    if (result?.sideEffectFailures?.length) throw new ConfigApplyError(result)
    return result
  }
  sendBytes<T>(method: string, path: string, body: Blob | Uint8Array | string, contentType = 'application/octet-stream'): Promise<T> {
    const payload = typeof body === 'string' || body instanceof Blob ? body : new Blob([new Uint8Array(body)])
    return fetch(`${this.config.apiUrl}${path}`, {
      method, headers: { ...this.config.headers, 'Content-Type': contentType }, body: payload,
      signal: AbortSignal.timeout(this.config.requestTimeoutMs),
    }).then(res => this.json<T>(res))
  }
  postForm<T>(path: string, form: FormData): Promise<T> {
    return fetch(`${this.config.apiUrl}${path}`, {
      method: 'POST', headers: { 'X-API-Key': this.config.apiKey }, body: form,
      signal: AbortSignal.timeout(this.config.requestTimeoutMs),
    }).then(res => this.json<T>(res))
  }
  /** Preserves named events, multiline data and UTF-8 split across chunks. */
  async *events(path: string, opts: { method?: string; body?: unknown; signal?: AbortSignal } = {}): AsyncGenerator<StreamEvent> {
    const res = await fetch(`${this.config.apiUrl}${path}`, {
      method: opts.method ?? 'GET', headers: this.config.headers,
      body: opts.body === undefined ? undefined : JSON.stringify(opts.body), signal: opts.signal,
    })
    if (!res.ok) await handleApiError(res)
    if (!res.body) return
    const reader = res.body.getReader(), decoder = new TextDecoder()
    let buffer = '', event = 'message', id: string | undefined, data: string[] = []
    const line = (text: string): StreamEvent | undefined => {
      if (text === '') {
        const result = data.length ? { event, data: data.join('\n'), id } : undefined
        event = 'message'; data = []
        return result
      }
      if (text.startsWith(':')) return
      const colon = text.indexOf(':')
      const field = colon < 0 ? text : text.slice(0, colon)
      const value = colon < 0 ? '' : text.slice(colon + 1).replace(/^ /, '')
      if (field === 'data') data.push(value)
      if (field === 'event') event = value
      if (field === 'id' && !value.includes('\0')) id = value
    }
    try {
      while (true) {
        const { done, value } = await reader.read()
        buffer += done ? decoder.decode() : decoder.decode(value, { stream: true })
        let end: number
        while ((end = buffer.indexOf('\n')) >= 0) {
          const result = line(buffer.slice(0, end).replace(/\r$/, ''))
          buffer = buffer.slice(end + 1)
          if (result) yield result
        }
        if (done) break
      }
    } finally { await reader.cancel(); reader.releaseLock() }
  }
  async *streamSse(path: string): AsyncGenerator<string> {
    for await (const event of this.events(path)) yield event.data
  }
}
