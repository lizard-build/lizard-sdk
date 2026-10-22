/**
 * The SDK's HTTP transport: one shared keep-alive connection pool for every request to Lizard.
 *
 * Plain `fetch` opens a new connection whenever none is idle at that instant, so a program that
 * starts many sandboxes at once paid a TLS handshake for nearly every request -- create, the first
 * command and the delete each on a fresh connection (10 sandboxes at once opened 37). Handshakes
 * run on Node's main thread, one after another, and that queue was most of a 100-sandbox burst's
 * time. Here requests share at most LIZARD_MAX_CONNECTIONS (default 16) kept-alive connections
 * per host and wait briefly for one instead (a 100-sandbox burst, create + first command: median
 * 1.3-1.6 s -> 1.0 s).
 *
 * Node only, through undici's own fetch and Agent (a matched pair; the Agent cannot be handed to
 * a different undici's fetch). Anywhere else, or where `fetch` was replaced (tests, a user's
 * polyfill or proxy wrapper), requests go to that `fetch` exactly as before.
 */

type Fetch = typeof fetch

const nativeFetch: Fetch | undefined = typeof globalThis.fetch === 'function' ? globalThis.fetch : undefined
let pooled: Promise<Fetch | null> | undefined

function isNode(): boolean {
  return typeof process !== 'undefined' && !!process.versions?.node
}

async function loadPooledFetch(): Promise<Fetch | null> {
  try {
    const undici = await import('undici')
    const max = Number(process.env.LIZARD_MAX_CONNECTIONS)
    const agent = new undici.Agent({
      connections: Number.isInteger(max) && max > 0 ? max : 16,
      keepAliveTimeout: 60_000,
      keepAliveMaxTimeout: 600_000,
    })
    return ((input: any, init?: any) => undici.fetch(input, { ...init, dispatcher: agent })) as unknown as Fetch
  } catch {
    return null
  }
}

/** `fetch` for requests to Lizard (see the module comment). */
export async function apiFetch(input: string | URL, init?: RequestInit): Promise<Response> {
  if (!isNode() || globalThis.fetch !== nativeFetch || process.env.LIZARD_POOLED_FETCH === '0') {
    return globalThis.fetch(input, init)
  }
  pooled ??= loadPooledFetch()
  const f = await pooled
  return (f ?? globalThis.fetch)(input, init)
}
