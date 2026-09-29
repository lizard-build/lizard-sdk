import { type PlatformClient, query } from './client'

export type MetricRange = '1h' | '6h' | '24h' | '7d' | '14d' | '30d'

export interface MetricPoint {
  t: number
  value: number
}

export interface ServiceMetrics {
  cpu: MetricPoint[]
  memory: MetricPoint[]
  networkRx: MetricPoint[]
  networkTx: MetricPoint[]
  diskRead: MetricPoint[]
  diskWrite: MetricPoint[]
}

export interface CostMetrics {
  compute: number
  egress: number
  storage: number
  total: number
  currency: string
}

export interface RawMetrics {
  timestamps: number[]
  series: Array<{ metric: string; values: number[]; available?: boolean[] }>
  latest?: Record<string, unknown>
  limits?: Record<string, number>
}
export interface ProjectCost { projectId: string; costUsd: number; [key: string]: unknown }

export class MetricsAPI {
  constructor(private readonly client: PlatformClient) {}
  service(id: string, range: MetricRange = '1h'): Promise<RawMetrics> {
    return this.client.get(`/api/apps/${id}/metrics?range=${range}`)
  }
  addon(projectId: string, addonId: string, range: MetricRange = '1h'): Promise<RawMetrics> {
    return this.client.get(`/api/projects/${projectId}/addons/${addonId}/metrics?range=${range}`)
  }
  project(id: string, opts: { range?: MetricRange; live?: boolean } = {}): Promise<unknown> {
    return this.client.get(query(`/api/projects/${id}/metrics`, opts))
  }
  private points(raw: RawMetrics, name: string): MetricPoint[] {
    const series = raw.series.find(s => s.metric === name)
    return (series?.values ?? []).flatMap((value, i) => series?.available?.[i] === false ? [] : [{ t: raw.timestamps[i], value }])
  }
  async cpu(id: string, range: MetricRange = '1h'): Promise<MetricPoint[]> { return this.points(await this.service(id, range), 'cpu') }
  async memory(id: string, range: MetricRange = '1h'): Promise<MetricPoint[]> { return this.points(await this.service(id, range), 'memory') }
  async network(id: string, range: MetricRange = '1h'): Promise<{ rx: MetricPoint[]; tx: MetricPoint[] }> {
    const raw = await this.service(id, range)
    return { rx: this.points(raw, 'network_rx'), tx: this.points(raw, 'network_tx') }
  }
  async disk(id: string, range: MetricRange = '1h'): Promise<{ read: MetricPoint[]; write: MetricPoint[] }> {
    const raw = await this.service(id, range)
    return { read: this.points(raw, 'disk_read'), write: this.points(raw, 'disk_write') }
  }
  async all(id: string, range: MetricRange = '1h'): Promise<ServiceMetrics> {
    const raw = await this.service(id, range)
    return { cpu: this.points(raw, 'cpu'), memory: this.points(raw, 'memory'), networkRx: this.points(raw, 'network_rx'), networkTx: this.points(raw, 'network_tx'), diskRead: this.points(raw, 'disk_read'), diskWrite: this.points(raw, 'disk_write') }
  }
  /** Return the backend's project cost row in USD, without guessing missing totals. */
  async cost(projectId: string, range: MetricRange = '30d'): Promise<ProjectCost | null> {
    const project = await this.client.get<{ workspaceId: string }>(`/api/projects/${projectId}`)
    const summary = await this.client.get<{ projects: ProjectCost[] }>(query('/api/billing/summary', { workspaceId: project.workspaceId, range }))
    return summary.projects.find(p => p.projectId === projectId) ?? null
  }
}
