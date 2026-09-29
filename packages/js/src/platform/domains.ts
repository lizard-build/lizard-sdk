import { type PlatformClient, segment } from './client'

export interface DomainInfo {
  domain: string
  /** 'pending' until DNS propagates and the platform verifies the CNAME/TXT record. */
  verified: boolean
  hostname?: string
  txtValue?: string
  live?: boolean
  generated?: boolean
  txtRecord?: string
  cnameTarget?: string
}

export class DomainsAPI {
  constructor(private readonly client: PlatformClient) {}

  /**
   * Show the current domain(s) for a service.
   * The platform-assigned `.onlizard.com` subdomain is always present.
   */
  async list(serviceId: string): Promise<DomainInfo[]> {
    const result = await this.info(serviceId)
    return [...result.domains.map(domain => ({ domain, verified: true, live: result.dnsOk?.[domain], cnameTarget: result.cnameTarget })),
      ...result.pending.map(item => ({ ...item, domain: item.hostname, verified: false }))]
  }
  info(serviceId: string): Promise<DomainStatus> { return this.client.get(`/api/apps/${serviceId}/domains`) }

  /**
   * Attach a custom domain to a service.
   * Returns the DNS records to add before calling `verify()`.
   *
   * @example
   * ```ts
   * const info = await lizard.domains.add(serviceId, 'api.example.com')
   * console.log('Add CNAME:', info.cnameTarget)
   * ```
   */
  async add(serviceId: string, domain: string, opts: { force?: boolean } = {}): Promise<DomainInfo> {
    const result = await this.client.post<DomainInfo>(`/api/apps/${serviceId}/domains`, { hostname: domain, ...opts })
    return { ...result, domain: result.hostname ?? domain }
  }

  /**
   * Verify that DNS records have propagated and activate the domain.
   * Call after adding the CNAME or TXT record returned by `add()`.
   */
  async verify(serviceId: string, domain: string): Promise<DomainInfo> {
    const result = await this.client.post<DomainInfo>(`/api/apps/${serviceId}/domains/verify`, { hostname: domain })
    return { ...result, domain: result.hostname ?? domain }
  }
  generate(serviceId: string): Promise<{ hostname: string; generated: boolean }> {
    return this.client.post(`/api/apps/${serviceId}/domains`, { generate: true })
  }
  delete(serviceId: string, hostname: string): Promise<void> {
    return this.client.delete(`/api/apps/${serviceId}/domains/${segment(hostname)}`)
  }
}

export interface DomainStatus {
  domain: string | null; domains: string[]; generatedDomain: string | null; cnameTarget: string
  dnsOk: Record<string, boolean>
  pending: Array<{ hostname: string; txtRecord: string; txtValue: string; cnameTarget: string }>
}
