import { createHash } from 'node:crypto'
import { ConnectionConfig } from './config'
import { LizardError, handleApiError } from './errors'
import type { SandboxOpts } from './sandbox/client'
import { apiFetch } from './transport'

interface ProjectRecord {
  id: string
  name?: string
  slug?: string
}

// Resolved project IDs are cached per (apiUrl, credential hash, ref) so repeated sandbox creates
// on the same Lizard client don't re-list projects on every call.
const projectIdCache = new Map<string, string>()

/**
 * Resolve a project reference — its ID, slug, or name — to the stable project
 * ID the API bills against. Only resources visible to this credential are used.
 *
 * @throws {LizardError} when the reference matches no project the key can see.
 */
export async function resolveProjectId(ref: string, config: ConnectionConfig): Promise<string> {
  const cacheKey = `${config.apiUrl}\0${createHash('sha256').update(config.apiKey).digest('hex')}\0${ref}`
  const cached = projectIdCache.get(cacheKey)
  if (cached) return cached

  const res = await apiFetch(`${config.apiUrl}/api/projects`, { headers: config.headers })
  if (!res.ok) await handleApiError(res)
  const projects = (await res.json()) as ProjectRecord[]

  const lower = ref.toLowerCase()
  const matches = projects.filter(
    (p) =>
      p.id.toLowerCase() === lower ||
      p.slug?.toLowerCase() === lower ||
      p.name?.toLowerCase() === lower
  )
  if (matches.length > 1) throw new LizardError('Project reference is ambiguous; pass the project ID')
  const match = matches[0]
  if (!match) {
    const available = projects.map((p) => p.slug || p.id).join(', ') || '(none)'
    throw new LizardError(
      `Project "${ref}" not found. Available: ${available}. ` +
        `Pass the project's ID, slug, or name.`
    )
  }

  projectIdCache.set(cacheKey, match.id)
  return match.id
}

/**
 * Every sandbox must belong to a project — billing is metered per project.
 * Returns the reference the caller gave, throwing when they gave none. Checked
 * before the connection is built so a missing project is reported as such,
 * rather than as a missing API key.
 */
export function requireProjectRef(opts: SandboxOpts | undefined): { projectId?: string; project?: string } {
  if (opts?.projectId) return { projectId: opts.projectId }
  if (opts?.project) return { project: opts.project }
  throw new LizardError(
    'A project is required to create a sandbox. Pass `project` (its ID, slug, or name), ' +
      'or create sandboxes through a Lizard client: new Lizard({ project: "my-project" }).'
  )
}

/**
 * Resolve the project a sandbox will be billed to: an exact `projectId` skips
 * the lookup, otherwise `project` (ID, slug, or name) is resolved.
 */
export async function resolveRequiredProjectId(
  opts: SandboxOpts | undefined,
  config: ConnectionConfig
): Promise<string> {
  const ref = requireProjectRef(opts)
  return ref.projectId ?? resolveProjectId(ref.project!, config)
}
