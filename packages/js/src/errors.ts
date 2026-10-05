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

/**
 * The account has to pay before it can do this (HTTP 402). Every create call answers
 * 402 when the account has no plan yet, its trial credits are used up, or an invoice
 * is unpaid. Show {@link message} to the user as is and send them to {@link url}.
 *
 * Still a {@link LizardError}, so existing `catch` blocks keep working.
 */
export class PaymentRequiredError extends LizardError {
  /**
   * Why payment is needed: `trial_available` (start the Pro trial),
   * `subscription_required` (the trial was used: start Pro), `trial_credits_used`
   * (start Pro now), `past_due` or `paused` (pay the open invoice), or, for accounts
   * on the old prepaid credits, `grace`, `frozen`, `card_required` or
   * `credits_required`. {@link LizardError.status} stays the HTTP status, 402.
   */
  paymentStatus?: string
  /** Billing page that starts the Pro trial, or Pro when the trial was used. */
  subscribeUrl?: string
  /** The Billing page. */
  billingUrl?: string
  /** The Credits page, for accounts on the old prepaid credits. */
  topupUrl?: string
  /** Stripe page that pays an unpaid invoice (`code` `UNPAID_INVOICE`). */
  invoiceUrl?: string

  constructor(message = 'Payment required') {
    super(message)
    this.name = 'PaymentRequiredError'
  }

  /** The one page to open next for this {@link paymentStatus}. */
  get url(): string | undefined {
    const s = this.paymentStatus
    if (this.invoiceUrl) return this.invoiceUrl
    if ((s === 'trial_available' || s === 'subscription_required') && this.subscribeUrl) return this.subscribeUrl
    if (s && PREPAID_STATUSES.has(s) && this.topupUrl) return this.topupUrl
    return this.billingUrl ?? this.subscribeUrl ?? this.topupUrl
  }
}

const PREPAID_STATUSES = new Set(['grace', 'frozen', 'card_required', 'credits_required'])
const ERROR_CODE = /^[A-Z][A-Z0-9_]*$/

export async function handleApiError(res: Response): Promise<never> {
  let body: Record<string, unknown> = {}
  try {
    const parsed: unknown = await res.json()
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) body = parsed as Record<string, unknown>
  } catch { /* not JSON */ }
  const text = (key: string) => typeof body[key] === 'string' && body[key] ? body[key] as string : undefined

  // Two shapes: {error: "human text", code?} and, on billing routes,
  // {error: "SCREAMING_CODE", message: "human text"} -- there the sentence is `message`
  // and the code is `error` unless the body also sends `code`.
  const error = text('error')
  const errorIsCode = !!error && ERROR_CODE.test(error)
  const message = (errorIsCode ? text('message') ?? error : error ?? text('message')) ?? res.statusText
  const code = text('code') ?? (errorIsCode ? error : undefined)

  let err: LizardError
  if (res.status === 402) {
    const paid = new PaymentRequiredError(message)
    paid.paymentStatus = text('status')
    paid.subscribeUrl = text('subscribeUrl')
    paid.billingUrl = text('billingUrl')
    paid.topupUrl = text('topupUrl')
    paid.invoiceUrl = text('invoiceUrl')
    err = paid
  }
  else if (res.status === 401 || res.status === 403) err = new AuthenticationError(message)
  else if (res.status === 404) err = new NotFoundError(message)
  else if (res.status === 409) err = new ConflictError(message)
  else if (res.status === 408 || res.status === 504) err = new TimeoutError(message)
  else err = new LizardError(`API error ${res.status}: ${message}`)
  err.status = res.status
  err.code = code
  throw err
}
