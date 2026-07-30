import type { PlatformClient } from './client'

export interface DomainInfo {
  domain: string
  /** 'pending' until DNS propagates and the platform verifies the CNAME/TXT record. */
  verified: boolean
  txtRecord?: string
  cnameTarget?: string
}

export class DomainsAPI {
  constructor(private readonly client: PlatformClient) {}

  /**
   * Show the current domain(s) for a service.
   * The platform-assigned `.onlizard.com` subdomain is always present.
   */
  list(serviceId: string): Promise<DomainInfo[]> {
    return this.client.get(`/api/apps/${serviceId}/domains`)
  }

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
  add(serviceId: string, domain: string): Promise<DomainInfo> {
    return this.client.post(`/api/apps/${serviceId}/domains`, { domain })
  }

  /**
   * Verify that DNS records have propagated and activate the domain.
   * Call after adding the CNAME or TXT record returned by `add()`.
   */
  verify(serviceId: string, domain: string): Promise<DomainInfo> {
    return this.client.post(`/api/apps/${serviceId}/domains/verify`, { domain })
  }
}
