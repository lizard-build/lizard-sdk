import { query, type PlatformClient } from './client'

/** Prepaid credits balance: old credits accounts (`plan: 'payg'`) until 1 November 2026, and enterprise usage. */
export interface Balance {
  plan: string
  status: 'active' | 'grace' | 'frozen' | string
  /** Current balance in cents. Negative means the account is in debt. */
  balanceCents: number
  overdraftLimitCents: number | null
  availableCents: number | null
  /** Current burn rate in cents per hour, across every running workload. */
  hourlyRateCents: number
  /** Hours of runway left at the current rate, or `null` when nothing is running. */
  runwayHours: number | null
  expiringCents: number
  expiringAt: number | null
  neverFreeze?: boolean
  invoicedMonthly?: boolean
  email?: string | null
}

export interface Transaction {
  id: string
  kind: string
  amountCents: number
  balanceAfterCents?: number
  description?: string
  createdAt: number
}

export interface TransactionPage {
  items: Transaction[]
  nextCursor: string | null
}

export interface ListTransactionsOpts {
  /** 1-100, default 20. */
  limit?: number
  /** `nextCursor` from a previous page. */
  cursor?: string
  /** Include the daily usage-deduction rows, which are otherwise omitted as noise. */
  includeUsage?: boolean
}

/**
 * `none`: no plan yet (creating anything answers 402). `pro`: the Pro subscription, see
 * {@link Subscription.status}. `payg`: old prepaid credits, until 1 November 2026.
 * `enterprise`: pay as you go, invoiced monthly.
 */
export type Plan = 'none' | 'pro' | 'payg' | 'enterprise'

/** Pro's tiers: `pro` (Pro, $19/month), `pro_99` (Pro 5x, $99) and `pro_499` (Pro 20x, $499). */
export type ProTier = 'pro' | 'pro_99' | 'pro_499'

/** One of Pro's tiers, as {@link Subscription.tiers} lists it. */
export interface ProTierOption {
  tier: ProTier | (string & {})
  /** Taxes included. */
  priceCents: number
  /** Usage included each paid month, in cents. */
  includedCents: number
  /** vCPU of Sandboxes the tier runs at once. */
  sandboxVcpu: number
  /** Only `pro` starts with a trial; the others charge their price from day one. */
  trial: boolean
  /** The account may buy it or move to it now. */
  available: boolean
}

/** Pro subscription status; `none` when there is no subscription. */
export type SubscriptionStatus = 'trialing' | 'active' | 'past_due' | 'canceled' | 'none'

export interface Subscription {
  plan: Plan | (string & {})
  status: SubscriptionStatus | (string & {})
  /** False when read for a workspace the caller does not own; card and invoice fields are then null. */
  isOwner: boolean
  /** The Pro tier; null without a live subscription. */
  tier: ProTier | (string & {}) | null
  /** A move to a lower tier that starts with the next period, or null. */
  pendingTier: ProTier | (string & {}) | null
  /** Of the current tier: 1900 for Pro ($19/month), 9900 for Pro 5x, 49900 for Pro 20x. */
  priceCents: number
  /** The price includes taxes. */
  taxIncluded: boolean
  /** Usage included each paid month, in cents, of the current tier. */
  includedCents: number
  /** Pro's three tiers, in order, and whether this account may have each. */
  tiers: ProTierOption[]
  trial: {
    /** The account can start a trial now. */
    eligible: boolean
    /** Trial length it would get, or got. */
    days: number | null
    /** Trial usage included, in cents. */
    creditCents: number | null
    /** Promo code held for the trial, if any. */
    promoCode: string | null
    /** Trial end (ms); null when not trialing. */
    endsAt: number | null
    /** Trial usage used (trialing only). */
    usedCents: number | null
    remainingCents: number | null
  }
  /** The current Pro period; null when there is none. */
  period: {
    kind: 'trial' | 'paid'
    start: number
    end: number
    /** 500 in the trial, 1900 in a paid month. */
    includedCents: number
    usedCents: number
    /** Paid month: usage above the included credits. */
    overageCents: number
    /** Of the overage, already invoiced. */
    billedOverageCents: number
    unbilledOverageCents: number
    /** Paid month: unbilled overage at which the next invoice goes out. */
    nextOverageChargeAtCents: number | null
  } | null
  /** Null when there is none, or the subscription is cancelling. */
  nextCharge: { at: number | null; amountCents: number } | null
  /** When a cancelled subscription ends (ms). */
  cancelAt: number | null
  /** An invoice is unpaid. */
  pastDue: boolean
  /** Stripe page that pays it (owner only). */
  openInvoiceUrl: string | null
  paymentMethod: { brand: string; last4: string; expMonth: number; expYear: number } | null
  /**
   * Pro only. `tier`: `trial` until the first paid invoice, then the Pro tier.
   * `sandboxVcpu`: vCPU of Sandboxes it runs at once; `maxSandboxCpus`: the largest sandbox, in vCPU.
   */
  limits: { tier: string; replicasPerApp: number; sandboxVcpu?: number; maxSandboxCpus?: number } | null
  /** Pro Checkout is open for this account. */
  checkoutAvailable: boolean
}

export interface StartCheckoutOpts {
  /** Dashboard path to come back to after Checkout, e.g. `/projects/abc`. */
  returnUrl?: string
  /** Default `pro`. `pro_99` and `pro_499` have no trial and charge their price today. */
  tier?: ProTier
}

/** What {@link BillingAPI.changeTier} did. */
export interface TierChange {
  /**
   * `upgraded`: charged the prorated difference now; the new limits apply at once.
   * `scheduled`: the move down starts with the next period ({@link effectiveAt}).
   * `unchanged`: already on that tier (a pending move down is cancelled).
   * `requires_action`: the bank wants a confirmation, or declined; open {@link invoiceUrl}.
   */
  status: 'upgraded' | 'scheduled' | 'unchanged' | 'requires_action' | (string & {})
  tier: ProTier | (string & {})
  pendingTier: ProTier | (string & {}) | null
  effectiveAt: number | null
  invoiceUrl: string | null
}

export interface CheckoutSession {
  /** Stripe Checkout page. The user finishes it in a browser. */
  url: string
  sessionId: string
  /** Null when the account already had a trial: Pro starts at once and charges $19. */
  trialDays: number | null
  trialCreditCents: number | null
}

export interface StartProNowResult {
  /**
   * `active`: charged $19, the first paid month started. `requires_action`: the bank
   * wants a confirmation (or declined); open `invoiceUrl`, the trial continues.
   * `failed`: nothing changed, the trial continues.
   */
  status: 'active' | 'requires_action' | 'failed'
  invoiceUrl?: string | null
}

export interface PromoRedemption {
  /** `pending_payment_method`: held for the trial Checkout starts. `applied`: applied now. */
  status: string
  code?: string
  /** The trial usage (older servers: the credit amount). */
  creditCents: number
  expiresAt: number | null
  /** Kept for older clients. */
  balanceCents: number
  /** Trial length the code gives. Missing from servers before Pro. */
  trialDays?: number
  trialCreditCents?: number
  /** `next_checkout`: held for the trial `startCheckout` opens. `current_trial`: extended the running trial. */
  appliesTo?: 'next_checkout' | 'current_trial'
}

/**
 * The account's plan, balance and usage.
 *
 * Pro costs $19/month, taxes included, with $19 of usage each month; usage above that
 * is pay as you go, invoiced as it builds up. A new account starts with a 7-day trial
 * with $5 of usage. Enterprise is pay as you go, invoiced monthly. Old prepaid
 * credits accounts (`plan: 'payg'`) keep {@link balance} and {@link transactions}
 * until 1 November 2026.
 *
 * Billing is **account-scoped, not workspace-scoped**: every workspace you create for
 * a user bills to the account that owns the key. That is what makes per-user
 * workspaces a safe pattern — your users get isolation, you keep one bill.
 *
 * **Requires an unscoped key**, except {@link subscription} with a `workspaceId` the
 * key can reach. A scoped key is refused with 403 `ACCOUNT_SCOPE_REQUIRED`, because a
 * scoped key is meant to be handed to an end user, who should not be reading your
 * card details or changing your plan. For per-workspace spend, use
 * {@link MetricsAPI.cost} instead.
 *
 * Checkout and invoices are web pages: methods return their URL for the user to open.
 * Nothing here retries a payment.
 */
export class BillingAPI {
  constructor(private readonly client: PlatformClient) {}

  /**
   * The plan: trial, this month's credits, overage, next charge, cancel date. With
   * `workspaceId`, the plan of that workspace's owner (`isOwner: false`, no card or
   * invoice fields).
   */
  subscription(opts?: { workspaceId?: string }): Promise<Subscription> {
    return this.client.get(query('/api/billing/subscription', { workspaceId: opts?.workspaceId }))
  }

  /**
   * Opens Stripe Checkout for Pro: the trial when the account can have one, otherwise
   * Pro at once ($19 today). With `tier`, Pro 5x or Pro 20x, charged today. Returns the page for the user to finish; a second call
   * while it is open returns the same session.
   */
  startCheckout(opts: StartCheckoutOpts = {}): Promise<CheckoutSession> {
    return this.client.post('/api/billing/subscription/checkout', { returnUrl: opts.returnUrl, tier: opts.tier })
  }

  /**
   * Moves a paid Pro subscription to another tier. Up: Stripe charges the prorated
   * difference now, this month's included usage rises by that charge, and the new limits
   * apply at once. Down: nothing is charged; the move starts with the next period. The
   * current tier cancels a pending move down. Refused during the trial (409 `TRIAL_ACTIVE`):
   * call {@link startProNow} first.
   */
  changeTier(tier: ProTier): Promise<TierChange> {
    return this.client.post('/api/billing/subscription/tier', { tier })
  }

  /** Ends the trial now: charges $19 and starts the first paid month with $19 of usage. */
  startProNow(): Promise<StartProNowResult> {
    return this.client.post('/api/billing/subscription/start-now', {})
  }

  /** Cancels Pro at the end of the current month or trial. Cancelling in the trial costs nothing. */
  cancel(): Promise<{ cancelAt: number | null }> {
    return this.client.post('/api/billing/subscription/cancel', {})
  }

  /** Undoes {@link cancel}: Pro renews as usual. */
  resume(): Promise<{ cancelAt: null }> {
    return this.client.post('/api/billing/subscription/resume', {})
  }

  /** Redeems a promo code: a longer trial with more trial usage. Works only before the first payment. */
  redeemPromo(code: string): Promise<PromoRedemption> {
    return this.client.post('/api/billing/promo/redeem', { code })
  }

  /** Prepaid credits balance, status, burn rate and runway (old `payg` accounts and enterprise). */
  balance(): Promise<Balance> {
    return this.client.get('/api/billing/balance')
  }

  /** A page of balance transactions, newest first (old `payg` accounts and enterprise). */
  transactions(opts?: ListTransactionsOpts): Promise<TransactionPage> {
    return this.client.get(query('/api/billing/transactions', {
      limit: opts?.limit,
      cursor: opts?.cursor || undefined,
      includeUsage: opts?.includeUsage ? '1' : undefined,
    }))
  }

  /** Cost summary for the current billing period, broken down by resource. */
  summary(): Promise<unknown> {
    return this.client.get('/api/billing/summary')
  }

  /** Live (not-yet-invoiced) usage accumulating right now. */
  live(): Promise<unknown> {
    return this.client.get('/api/billing/live')
  }

  /** Saved cards. Cards are added in Checkout or on the Billing page. */
  paymentMethods(): Promise<{ items: unknown[] }> {
    return this.client.get('/api/billing/payment-methods')
  }

  removePaymentMethod(id: string): Promise<void> {
    return this.client.delete(`/api/billing/payment-methods/${encodeURIComponent(id)}`)
  }
}
