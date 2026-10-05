/**
 * The SDK is meant to reach everything `lizard` the CLI reaches. These cover the
 * pieces that were missing or wrong, with fetch stubbed — no network.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { Lizard } from './lizard'
import { Sandbox } from './sandbox'
import { Volume } from './volume'
import { AuthenticationError, ConflictError, LizardError, PaymentRequiredError, TimeoutError } from './errors'

const API = 'https://api.parity.invalid'
const opts = { apiKey: 'liz_test', apiUrl: API }

/** Record every request, answer each with the queued response. */
function stubFetch(responses: Array<{ status?: number; body: unknown }>) {
  const calls: Array<{ url: string; method: string; body: any }> = []
  let i = 0
  const fn = vi.fn(async (url: any, init?: any) => {
    calls.push({
      url: String(url),
      method: init?.method ?? 'GET',
      body: init?.body ? JSON.parse(init.body) : undefined,
    })
    const r = responses[Math.min(i++, responses.length - 1)]
    return {
      ok: (r.status ?? 200) < 400,
      status: r.status ?? 200,
      headers: new Map([['content-length', '1']]) as any,
      json: async () => r.body,
      text: async () => JSON.stringify(r.body),
    } as any
  })
  vi.stubGlobal('fetch', fn)
  return calls
}

beforeEach(() => { vi.unstubAllGlobals() })
afterEach(() => { vi.unstubAllGlobals() })

describe('region', () => {
  it('sends region on volume create', async () => {
    const calls = stubFetch([{ body: { id: 'v1', name: 'data' } }])
    await Volume.create('p1', 'data', { sizeGb: 3, region: 'us-east-1', ...opts })
    expect(calls[0].body).toMatchObject({ name: 'data', sizeGb: 3, region: 'us-east-1' })
  })

  it('sends region on getOrCreate too', async () => {
    const calls = stubFetch([{ body: { id: 'v1', name: 'data' } }])
    await Volume.getOrCreate('p1', 'data', { region: 'eu-west-lim-a', ...opts })
    expect(calls[0].body).toMatchObject({ region: 'eu-west-lim-a', getOrCreate: true })
  })

  it('sends region on sandbox create', async () => {
    const calls = stubFetch([{ body: { sandboxId: 's1' } }])
    await Sandbox.create('codex', { projectId: 'p1', region: 'us-east-1', ...opts })
    expect(calls[0].body).toMatchObject({ template: 'codex', region: 'us-east-1' })
  })

  it('omits region when not given, so the server can take it from the volume', async () => {
    const calls = stubFetch([{ body: { sandboxId: 's1' } }])
    await Sandbox.create('codex', { projectId: 'p1', volumeName: 'data', ...opts })
    expect(calls[0].body.region).toBeUndefined()
    expect(calls[0].body.volumeName).toBe('data')
  })
})

describe('connect', () => {
  it('reads the sandbox instead of resuming it', async () => {
    // resume is a hard 501 on every sandbox; connecting must not touch it.
    const calls = stubFetch([{ body: { sandboxId: 's1', template: 'codex' } }])
    const sb = await Sandbox.connect('s1', opts)
    expect(sb.sandboxId).toBe('s1')
    expect(calls).toHaveLength(1)
    expect(calls[0].method).toBe('GET')
    expect(calls[0].url).toBe(`${API}/api/sandboxes/s1`)
    expect(calls[0].url).not.toContain('resume')
  })

  it('propagates a 404 rather than returning a dead handle', async () => {
    stubFetch([{ status: 404, body: { error: 'Sandbox not found' } }])
    await expect(Sandbox.connect('gone', opts)).rejects.toThrow()
  })
})

describe('provisioning surfaces', () => {
  it('creates a workspace', async () => {
    const calls = stubFetch([{ body: { id: 'w1', name: 'u-1', slug: 'u-1' } }])
    const ws = await new Lizard(opts).workspaces.create({ name: 'u-1' })
    expect(ws.id).toBe('w1')
    expect(calls[0]).toMatchObject({ url: `${API}/api/workspaces`, method: 'POST', body: { name: 'u-1' } })
  })

  it('deletes a workspace empty-only by default', async () => {
    const calls = stubFetch([{ status: 204, body: {} }])
    await new Lizard(opts).workspaces.delete('w1')
    expect(calls[0].url).toBe(`${API}/api/workspaces/w1?requireEmpty=true`)
  })

  it('only drops that guard when force is explicit', async () => {
    const calls = stubFetch([{ status: 204, body: {} }])
    await new Lizard(opts).workspaces.delete('w1', { force: true })
    expect(calls[0].url).toBe(`${API}/api/workspaces/w1`)
  })

  it('folds workspaces and projects into one scopes array', async () => {
    const calls = stubFetch([{ body: { id: 'k1', name: 'k', key: 'liz_secret', scopes: [] } }])
    const key = await new Lizard(opts).apiKeys.create({ name: 'k', workspaces: ['w1'], projects: ['p1'] })
    expect(key.key).toBe('liz_secret')
    expect(calls[0].body.scopes).toEqual([
      { type: 'workspace', id: 'w1' },
      { type: 'project', id: 'p1' },
    ])
  })

  it('lists regions and reads the balance', async () => {
    stubFetch([{ body: [{ id: 'us-east-1' }] }])
    expect((await new Lizard(opts).regions.list())[0].id).toBe('us-east-1')

    stubFetch([{ body: { plan: 'payg', status: 'active', balanceCents: -5, hourlyRateCents: 22 } }])
    expect((await new Lizard(opts).billing.balance()).hourlyRateCents).toBe(22)
  })

  it('reads the Pro plan, for the account or a workspace owner', async () => {
    const plan = { plan: 'pro', status: 'active', isOwner: false, period: { kind: 'paid', includedCents: 1900, usedCents: 3140, overageCents: 1240 } }
    const calls = stubFetch([{ body: plan }])
    const sub = await new Lizard(opts).billing.subscription({ workspaceId: 'w 1' })
    expect(calls[0].url).toBe(`${API}/api/billing/subscription?workspaceId=w+1`)
    expect(sub.period?.overageCents).toBe(1240)
    expect(sub.isOwner).toBe(false)
  })

  it('starts Checkout, starts Pro now, cancels and resumes', async () => {
    const calls = stubFetch([
      { body: { url: 'https://checkout.test/cs_1', sessionId: 'cs_1', trialDays: null, trialCreditCents: null } },
      { body: { status: 'active' } },
      { body: { cancelAt: 1791800000000 } },
      { body: { cancelAt: null } },
    ])
    const billing = new Lizard(opts).billing
    expect((await billing.startCheckout()).trialDays).toBeNull()
    expect((await billing.startProNow()).status).toBe('active')
    expect((await billing.cancel()).cancelAt).toBe(1791800000000)
    expect((await billing.resume()).cancelAt).toBeNull()
    expect(calls.map((c) => [c.method, c.url.slice(API.length), c.body])).toEqual([
      ['POST', '/api/billing/subscription/checkout', {}],
      ['POST', '/api/billing/subscription/start-now', {}],
      ['POST', '/api/billing/subscription/cancel', {}],
      ['POST', '/api/billing/subscription/resume', {}],
    ])
  })

  it('returns the trial a promo code gives', async () => {
    stubFetch([{ body: { status: 'applied', code: 'ROST', creditCents: 10000, expiresAt: 1, balanceCents: 0, trialDays: 31, trialCreditCents: 10000, appliesTo: 'current_trial' } }])
    const out = await new Lizard(opts).billing.redeemPromo('ROST')
    expect(out).toMatchObject({ trialDays: 31, trialCreditCents: 10000, appliesTo: 'current_trial' })
  })

  it('no longer has the credit purchase, auto top-up or x402 methods', () => {
    const billing = new Lizard(opts).billing as unknown as Record<string, unknown>
    for (const gone of ['purchase', 'autoTopup', 'setAutoTopup', 'runAutoTopup', 'x402Quote', 'payX402', 'paymentStatus', 'setupPaymentMethod']) {
      expect(billing[gone]).toBeUndefined()
    }
  })

  it('builds the transactions query from its options', async () => {
    const calls = stubFetch([{ body: { items: [], nextCursor: null } }])
    await new Lizard(opts).billing.transactions({ limit: 5, includeUsage: true })
    expect(calls[0].url).toBe(`${API}/api/billing/transactions?limit=5&includeUsage=1`)
  })
})

describe('project-bound volumes', () => {
  it('fills in the project id so callers do not repeat it', async () => {
    const calls = stubFetch([
      { body: [{ id: 'p_abc', name: 'proj', slug: 'proj' }] }, // project resolution
      { body: { id: 'v1', name: 'scratch' } },                  // the volume create
    ])
    const vol = await new Lizard({ ...opts, project: 'proj' }).volumes.getOrCreate('scratch', { sizeGb: 7 })
    expect(vol.volumeId).toBe('v1')
    expect(calls[1].url).toBe(`${API}/api/projects/p_abc/volumes`)
    expect(calls[1].body).toMatchObject({ name: 'scratch', sizeGb: 7, getOrCreate: true })
  })
})

describe('volume resize', () => {
  const info = { id: 'v1', projectId: 'p1', name: 'my data', sizeGb: 20, status: 'ready', createdAt: 1, sizeEnforced: true }

  it('PATCHes the volume by encoded name with the new size, and returns its info', async () => {
    const calls = stubFetch([{ body: info }])
    const out = await Volume.resize('p1', 'my data/x', 20, opts)
    expect(calls).toHaveLength(1)
    expect(calls[0].method).toBe('PATCH')
    expect(calls[0].url).toBe(`${API}/api/projects/p1/volumes/my%20data%2Fx`)
    expect(calls[0].body).toEqual({ sizeGb: 20 })
    expect(out.sizeGb).toBe(20)
    expect(out.sizeEnforced).toBe(true)
  })

  it('resizes from a held Volume by its id', async () => {
    const calls = stubFetch([{ body: info }])
    const vol = new Volume({ volumeId: 'v1', name: 'data', ...opts })
    const out = await vol.resize('p1', 3)
    expect(calls[0].method).toBe('PATCH')
    expect(calls[0].url).toBe(`${API}/api/projects/p1/volumes/v1`)
    expect(calls[0].body).toEqual({ sizeGb: 3 })
    expect(out.id).toBe('v1')
  })

  it('is on the project-bound lizard.volumes', async () => {
    const calls = stubFetch([
      { body: [{ id: 'p_rsz', name: 'rsz-proj', slug: 'rsz-proj' }] },
      { body: info },
    ])
    await new Lizard({ ...opts, project: 'rsz-proj' }).volumes.resize('scratch', 12)
    expect(calls[1].method).toBe('PATCH')
    expect(calls[1].url).toBe(`${API}/api/projects/p_rsz/volumes/scratch`)
    expect(calls[1].body).toEqual({ sizeGb: 12 })
  })

  it('keeps the server error code on a refused shrink', async () => {
    stubFetch([{ status: 409, body: { error: 'Volume too full to shrink', code: 'volume_too_full_to_shrink' } }])
    const err = await Volume.resize('p1', 'data', 1, opts).catch((e) => e)
    expect(err).toBeInstanceOf(ConflictError)
    expect(err.code).toBe('volume_too_full_to_shrink')
    expect(err.status).toBe(409)
    expect(err.message).toBe('Volume too full to shrink')
  })

  it('surfaces a resize timeout as TimeoutError with its code', async () => {
    stubFetch([{ status: 504, body: { error: 'Resize timed out', code: 'volume_resize_timeout' } }])
    const err = await Volume.resize('p1', 'data', 50, opts).catch((e) => e)
    expect(err).toBeInstanceOf(TimeoutError)
    expect(err.code).toBe('volume_resize_timeout')
  })

  it('keeps the code on errors without a dedicated class', async () => {
    stubFetch([{ status: 503, body: { error: 'No capacity', code: 'volume_capacity_unavailable' } }])
    const err = await Volume.resize('p1', 'data', 50, opts).catch((e) => e)
    expect(err).toBeInstanceOf(LizardError)
    expect(err.code).toBe('volume_capacity_unavailable')
    expect(err.status).toBe(503)
  })
})

describe('payment required (HTTP 402)', () => {
  const body = {
    error: 'INSUFFICIENT_CREDITS',
    code: 'PAYMENT_REQUIRED',
    status: 'trial_available',
    message: 'Start your 7-day Pro trial with $5 in credits to deploy. No charge today, then $19/month.',
    subscribeUrl: 'https://lizard.build/profile/account-billing?subscribe=1',
    billingUrl: 'https://lizard.build/profile/account-billing',
    topupUrl: 'https://lizard.build/profile/account-credits',
    balanceCents: 0,
    availableCents: 100,
  }

  it('raises PaymentRequiredError with the sentence, the code and the links', async () => {
    stubFetch([{ status: 402, body }])
    const err = await new Lizard(opts).projects.create({ workspaceId: 'w1', name: 'x' }).catch((e) => e)
    expect(err).toBeInstanceOf(PaymentRequiredError)
    expect(err).toBeInstanceOf(LizardError)
    expect(err.name).toBe('PaymentRequiredError')
    expect(err.status).toBe(402)
    expect(err.code).toBe('PAYMENT_REQUIRED')
    expect(err.message).toBe(body.message)
    expect(err.paymentStatus).toBe('trial_available')
    expect(err.subscribeUrl).toBe(body.subscribeUrl)
    expect(err.billingUrl).toBe(body.billingUrl)
    expect(err.url).toBe(body.subscribeUrl)
  })

  it('reads older servers that send only error: INSUFFICIENT_CREDITS', async () => {
    stubFetch([{ status: 402, body: { error: 'INSUFFICIENT_CREDITS', status: 'frozen', message: 'Your credits are used up.', topupUrl: body.topupUrl } }])
    const err = await Sandbox.create('base', { ...opts, projectId: 'p1' }).catch((e) => e)
    expect(err).toBeInstanceOf(PaymentRequiredError)
    expect(err.code).toBe('INSUFFICIENT_CREDITS')
    expect(err.message).toBe('Your credits are used up.')
    expect(err.billingUrl).toBeUndefined()
    expect(err.url).toBe(body.topupUrl)
  })

  it.each([
    ['past_due', body.billingUrl],
    ['trial_credits_used', body.billingUrl],
    ['subscription_required', body.subscribeUrl],
  ])('%s points at the right page', async (status, url) => {
    stubFetch([{ status: 402, body: { ...body, status } }])
    const err = await Volume.create('p1', 'data', opts).catch((e) => e)
    expect(err).toBeInstanceOf(PaymentRequiredError)
    expect(err.url).toBe(url)
  })

  it('an unpaid invoice links the invoice', async () => {
    stubFetch([{ status: 402, body: { error: 'UNPAID_INVOICE', message: 'Pay your open invoice before starting Pro again', invoiceUrl: 'https://invoice.stripe.com/i/x' } }])
    const err = await new Lizard(opts).regions.list().catch((e) => e)
    expect(err).toBeInstanceOf(PaymentRequiredError)
    expect(err.code).toBe('UNPAID_INVOICE')
    expect(err.url).toBe('https://invoice.stripe.com/i/x')
  })

  it('coded billing errors keep the sentence and the code on every status', async () => {
    stubFetch([{ status: 409, body: { error: 'ALREADY_SUBSCRIBED', message: 'This account already has Pro' } }])
    const conflict = await new Lizard(opts).projects.create({ workspaceId: 'w1', name: 'x' }).catch((e) => e)
    expect(conflict).toBeInstanceOf(ConflictError)
    expect(conflict.message).toBe('This account already has Pro')
    expect(conflict.code).toBe('ALREADY_SUBSCRIBED')

    stubFetch([{ status: 403, body: { error: 'ACCOUNT_SCOPE_REQUIRED', message: 'Billing needs an unscoped key.' } }])
    const scoped = await new Lizard(opts).billing.balance().catch((e) => e)
    expect(scoped).toBeInstanceOf(AuthenticationError)
    expect(scoped.message).toBe('Billing needs an unscoped key.')
    expect(scoped.code).toBe('ACCOUNT_SCOPE_REQUIRED')
  })
})
