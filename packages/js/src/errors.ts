export class LizardError extends Error {
  /** HTTP status of the failed API call, when the error came from one. */
  status?: number
  /**
   * The server's machine-readable error code, when it sent one — e.g.
   * `'volume_too_full_to_shrink'`. Branch on this rather than on `message`.
   */
  code?: string

  constructor(message: string) {
    super(message)
    this.name = 'LizardError'
  }
}

/** Config was saved, but one or more deploy/restart actions failed. Never retry blindly. */
export class ConfigApplyError extends LizardError {
  constructor(readonly result: unknown) {
    super('Config was saved, but one or more side effects failed; inspect result before retrying')
    this.name = 'ConfigApplyError'
  }
}

export class AuthenticationError extends LizardError {
  constructor(message = 'Invalid or missing API key') {
    super(message)
    this.name = 'AuthenticationError'
  }
}

export class NotFoundError extends LizardError {
  constructor(message = 'Sandbox not found') {
    super(message)
    this.name = 'NotFoundError'
  }
}

/**
 * The resource already exists — most often a volume whose name is already taken in
 * the project. Volume names are the key inside a project, so `Volume.create` refuses
 * to make a second one; catch this, or call `Volume.getOrCreate` instead.
 */
export class ConflictError extends LizardError {
  constructor(message = 'Resource already exists') {
    super(message)
    this.name = 'ConflictError'
  }
}

export class TimeoutError extends LizardError {
  constructor(message = 'Sandbox operation timed out') {
    super(message)
    this.name = 'TimeoutError'
  }
}

export async function handleApiError(res: Response): Promise<never> {
  let message: string
  let code: string | undefined
  try {
    const body = await res.json() as { error?: string; code?: unknown }
    message = body.error ?? res.statusText
    if (typeof body.code === 'string') code = body.code
  } catch {
    message = res.statusText
  }

  let err: LizardError
  if (res.status === 401 || res.status === 403) err = new AuthenticationError(message)
  else if (res.status === 404) err = new NotFoundError(message)
  else if (res.status === 409) err = new ConflictError(message)
  else if (res.status === 408 || res.status === 504) err = new TimeoutError(message)
  else err = new LizardError(`API error ${res.status}: ${message}`)
  err.status = res.status
  err.code = code
  throw err
}
