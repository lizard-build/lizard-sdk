export class LizardError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'LizardError'
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

export class TimeoutError extends LizardError {
  constructor(message = 'Sandbox operation timed out') {
    super(message)
    this.name = 'TimeoutError'
  }
}

export async function handleApiError(res: Response): Promise<never> {
  let message: string
  try {
    const body = await res.json() as { error?: string }
    message = body.error ?? res.statusText
  } catch {
    message = res.statusText
  }

  if (res.status === 401 || res.status === 403) throw new AuthenticationError(message)
  if (res.status === 404) throw new NotFoundError(message)
  if (res.status === 408 || res.status === 504) throw new TimeoutError(message)
  throw new LizardError(`API error ${res.status}: ${message}`)
}
