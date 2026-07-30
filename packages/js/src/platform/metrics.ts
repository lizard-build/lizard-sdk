import type { PlatformClient } from './client'

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

export class MetricsAPI {
  constructor(private readonly client: PlatformClient) {}

  /** Get CPU metrics for a service or addon. */
  cpu(id: string, range: MetricRange = '1h'): Promise<MetricPoint[]> {
    return this.client.get(`/api/apps/${id}/metrics/cpu?range=${range}`)
  }

  /** Get memory metrics for a service or addon. */
  memory(id: string, range: MetricRange = '1h'): Promise<MetricPoint[]> {
    return this.client.get(`/api/apps/${id}/metrics/memory?range=${range}`)
  }

  /** Get network I/O metrics for a service. */
  network(id: string, range: MetricRange = '1h'): Promise<{ rx: MetricPoint[]; tx: MetricPoint[] }> {
    return this.client.get(`/api/apps/${id}/metrics/network?range=${range}`)
  }

  /** Get disk I/O metrics for a service. */
  disk(id: string, range: MetricRange = '1h'): Promise<{ read: MetricPoint[]; write: MetricPoint[] }> {
    return this.client.get(`/api/apps/${id}/metrics/disk?range=${range}`)
  }

  /**
   * Get cost breakdown for a project over the given range.
   * Costs are in USD cents unless the `currency` field says otherwise.
   */
  cost(projectId: string, range: MetricRange = '30d'): Promise<CostMetrics> {
    return this.client.get(`/api/projects/${projectId}/metrics/cost?range=${range}`)
  }

  /**
   * Convenience: fetch all metric types for a service in one call.
   */
  async all(id: string, range: MetricRange = '1h'): Promise<ServiceMetrics> {
    const [cpu, memory, network, disk] = await Promise.all([
      this.cpu(id, range),
      this.memory(id, range),
      this.network(id, range),
      this.disk(id, range),
    ])
    return { cpu, memory, networkRx: network.rx, networkTx: network.tx, diskRead: disk.read, diskWrite: disk.write }
  }
}
