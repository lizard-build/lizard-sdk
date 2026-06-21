export const DEFAULT_API_URL = 'https://api.lizard.run'
export const DEFAULT_SANDBOX_TIMEOUT_MS = 5 * 60 * 1000 // 5 minutes

export interface ConnectionOpts {
  apiKey?: string
  apiUrl?: string
  timeoutMs?: number
  requestTimeoutMs?: number
}

export class ConnectionConfig {
  readonly apiKey: string
  readonly apiUrl: string
  readonly timeoutMs: number

  constructor(opts?: ConnectionOpts) {
    this.apiKey = opts?.apiKey ?? process.env.LIZARD_API_KEY ?? ''
    this.apiUrl = opts?.apiUrl ?? process.env.LIZARD_API_URL ?? DEFAULT_API_URL
    this.timeoutMs = opts?.timeoutMs ?? DEFAULT_SANDBOX_TIMEOUT_MS

    if (!this.apiKey) {
      throw new Error(
        'Lizard API key is required. Set LIZARD_API_KEY env var or pass apiKey in options.'
      )
    }
  }

  get headers(): Record<string, string> {
    return {
      'X-API-Key': this.apiKey,
      'Content-Type': 'application/json',
    }
  }
}
