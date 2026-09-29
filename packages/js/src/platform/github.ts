import type { PlatformClient } from './client'
import { ServicesAPI } from './services'

export class GitHubAPI {
  constructor(private readonly client: PlatformClient) {}
  status(): Promise<unknown> { return this.client.get('/api/github/status') }
  /** Complete the GitHub App installation in a browser using the caller's account. */
  installUrl(): string { return `${this.client.config.apiUrl}/api/auth/github/install` }
  async checkout(serviceId: string, branch: string) {
    const services = new ServicesAPI(this.client)
    await services.update(serviceId, { branch })
    return services.redeploy(serviceId)
  }
}
