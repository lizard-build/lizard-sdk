import type { PlatformClient } from './client'

export interface Region {
  id: string
  name?: string
  label?: string
  country?: string
  city?: string
  /** False for a region that exists but is not accepting new workloads. */
  available?: boolean
  isDefault?: boolean
}

/**
 * The regions workloads can be placed in.
 *
 * Region ids are what `Sandbox.create({ region })` and `Volume.create({ region })`
 * take, so this is how you discover a valid value rather than hardcoding one.
 *
 * @example
 * ```ts
 * const regions = await lizard.regions.list()
 * console.log(regions.map(r => r.id)) // ['eu-west-lim-a', 'us-east-1', ...]
 * ```
 */
export class RegionsAPI {
  constructor(private readonly client: PlatformClient) {}

  /** List every region, including ones not currently accepting workloads. */
  list(): Promise<Region[]> {
    return this.client.get('/api/regions')
  }
}
