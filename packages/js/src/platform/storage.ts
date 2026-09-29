import { type PlatformClient, query, segment } from './client'

export class StorageAPI {
  constructor(private readonly client: PlatformClient) {}
  list(projectId: string, addonId: string, opts: { bucket?: string; prefix?: string } = {}): Promise<unknown> {
    return this.client.get(query(`/api/projects/${projectId}/addons/${addonId}/s3/buckets/${segment(opts.bucket ?? 'default')}/objects`, { prefix: opts.prefix }))
  }
  upload(projectId: string, addonId: string, opts: { key: string; source: Blob | Uint8Array | string; bucket?: string; contentType?: string }): Promise<{ key: string; etag: string; size: number; url: string | null }> {
    const key = opts.key.split('/').map(segment).join('/')
    return this.client.sendBytes('PUT', `/api/projects/${projectId}/addons/${addonId}/s3/objects/${segment(opts.bucket ?? 'default')}/${key}`, opts.source, opts.contentType)
  }
}
