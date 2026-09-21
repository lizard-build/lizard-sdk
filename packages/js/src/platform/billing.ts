import type { PlatformClient } from './client'

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
 * Account balance and usage.
 *
 * Billing is **account-scoped, not workspace-scoped**: every workspace you create for
 * a user bills to the account that owns the key. That is what makes per-user
 * workspaces a safe pattern — your users get isolation, you keep one bill — and also
 * what makes {@link Balance.runwayHours} worth watching before you provision more.
 *
 * **Requires an unscoped key.** A scoped key is refused with 403
 * `ACCOUNT_SCOPE_REQUIRED`, because there is no workspace-scoped view of one shared
 * balance, ledger and set of saved cards — and because a scoped key is meant to be
 * handed to an end user, who should not be reading your card details or spending
 * against them. For per-workspace spend, use {@link MetricsAPI.cost} instead.
 */
export class BillingAPI {
  constructor(private readonly client: PlatformClient) {}

  /** Current balance, status, burn rate, and runway. */
  balance(): Promise<Balance> {
    return this.client.get('/api/billing/balance')
  }

  /** A page of balance transactions, newest first. */
  transactions(opts?: ListTransactionsOpts): Promise<TransactionPage> {
    const qs = new URLSearchParams()
    if (opts?.limit !== undefined) qs.set('limit', String(opts.limit))
    if (opts?.cursor) qs.set('cursor', opts.cursor)
    if (opts?.includeUsage) qs.set('includeUsage', '1')
    const q = qs.toString()
    return this.client.get(`/api/billing/transactions${q ? `?${q}` : ''}`)
  }

  /** Cost summary for the current billing period, broken down by resource. */
  summary(): Promise<unknown> {
    return this.client.get('/api/billing/summary')
  }

  /** Live (not-yet-invoiced) usage accumulating right now. */
  live(): Promise<unknown> {
    return this.client.get('/api/billing/live')
  }
}
