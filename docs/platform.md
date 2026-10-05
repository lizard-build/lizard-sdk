# Platform guide

[Sandbox reference](sandboxes.md) · [CLI coverage and migration](cli-parity.md)

Use `Lizard` to manage cloud apps, databases, storage, projects and credentials. Platform methods do not require a default project; pass resource IDs to each method.

```ts
import { Lizard } from '@lizard-build/sdk'

const lizard = new Lizard({})
const projects = await lizard.projects.list()
console.log(projects.map(project => ({ id: project.id, name: project.name })))
```

```python
from lizard import Lizard

lizard = Lizard()
for project in lizard.projects.list():
    print(project.id, project.name)
```

Both clients read `LIZARD_API_KEY`. To create sandboxes or use project-bound volumes, pass `project` to `Lizard`.

## API namespaces

| TypeScript | Python | Purpose |
| --- | --- | --- |
| `projects` | `projects` | Projects, config, services and project logs |
| `services` | `services` | Deploy, inspect, scale and run commands in apps |
| `addons` | `addons` | Managed databases and other addons |
| `secrets` | `secrets` | Environment variables and secret references |
| `domains` | `domains` | App domains and DNS verification |
| `storage` | `storage` | S3 object listing and uploads |
| `github` | `github` | GitHub connection status and checkout |
| `metrics` | `metrics` | Resource use and project costs |
| `workspaces` | `workspaces` | Workspaces and resource ownership |
| `apiKeys` | `api_keys` | API keys and scopes |
| `regions` | `regions` | Available regions |
| `billing` | `billing` | The account's plan, Pro Checkout, promo codes, balance and transactions |
| `volumes` | `volumes` | Persistent files for sandboxes in the client's project |

`whoami()` returns the account identity visible to the credential. `platform` exposes the underlying HTTP client for endpoints without a dedicated method. See [CLI coverage](cli-parity.md#native-apis) for the method map.

## Workspaces and scoped keys

For an application with separate users, you can create a workspace and project for each user, then issue a key scoped to that workspace. Run this from your trusted application server with a key that has access to create these resources.

```ts
import { Lizard } from '@lizard-build/sdk'

const lizard = new Lizard({})
const workspace = await lizard.workspaces.create({ name: 'example-user' })
const project = await lizard.projects.create({ workspaceId: workspace.id, name: 'default' })
const key = await lizard.apiKeys.create({
  name: 'example-user',
  workspaces: [workspace.id],
})
// Store key.key in your secret store now; the API returns it only once.
```

```python
from lizard import Lizard

lizard = Lizard()
workspace = lizard.workspaces.create(name="example-user")
project = lizard.projects.create(workspace_id=workspace.id, name="default")
key = lizard.api_keys.create(name="example-user", workspaces=[workspace.id])
# Store key.key in your secret store now; the API returns it only once.
```

A key with no scopes has access to all resources the creating account can reach. Pass `workspaces` or `projects` to limit that access. Scoped keys cannot create broader keys.

If tools inside a sandbox need Lizard access, pass a scoped key through `lizardToken` / `lizard_token`. Any code in that sandbox can read the key and use its permissions. Choose a template with the CLI installed when running CLI commands.

### Account and billing access

Billing belongs to the account, across all its workspaces. Scoped keys cannot access account billing or account-wide usage; those routes return HTTP 403 with `ACCOUNT_SCOPE_REQUIRED`. The one exception is `billing.subscription({ workspaceId })` / `billing.subscription(workspace_id=...)`, which any member's key that reaches the workspace can call to see why the owner's account is blocked; it leaves out the card and invoice. A scoped key's `whoami()` response includes identity and scopes, without the account's email, balance or plan. Use scoped `metrics` calls for project costs.

`workspaces.delete()` requires an empty workspace by default. The `force` option removes the workspace and its resources. Revoking a key or deleting a resource takes effect immediately.

## Billing

Pro costs $19/month, taxes included, with $19 of credits each month for everything on the account. Usage above that is pay as you go, invoiced as it builds up. A new account starts with a 7-day trial with $5 of credits; Checkout asks for a card and charges nothing until the trial ends. Promo codes give a longer trial with more trial credits and work only before the first payment. Enterprise accounts pay as you go, invoiced monthly. Accounts on the old prepaid credits (`plan: "payg"`) keep `balance()` and `transactions()` until November 1, 2026. There are no top-ups and no crypto or x402 payments.

```ts
const sub = await lizard.billing.subscription()
if (sub.plan === 'none' && sub.trial.eligible) {
  const { url } = await lizard.billing.startCheckout({ returnUrl: '/' })
  console.log(`Start your ${sub.trial.days}-day trial: ${url}`)
} else if (sub.period) {
  console.log(`$${(sub.period.usedCents / 100).toFixed(2)} of $${sub.period.includedCents / 100} used`)
}
```

```python
sub = lizard.billing.subscription()
if sub.plan == "none" and sub.trial.eligible:
    session = lizard.billing.start_checkout(return_url="/")
    print(f"Start your {sub.trial.days}-day trial: {session.url}")
elif sub.period:
    print(f"${sub.period.used_cents / 100:.2f} of ${sub.period.included_cents // 100} used")
```

| TypeScript | Python | What it does |
| --- | --- | --- |
| `subscription({ workspaceId? })` | `subscription(workspace_id=None)` | Plan, trial days and credits left, this month's credits and overage, next charge, cancel date, unpaid invoice |
| `startCheckout({ returnUrl? })` | `start_checkout(return_url=None)` | Stripe Checkout URL for the trial, or for Pro at once when the trial was used |
| `startProNow()` | `start_pro_now()` | End the trial: charge $19 now and start the first paid month. `requires_action` returns an invoice page to open |
| `cancel()` | `cancel()` | Cancel at the end of the month or trial; returns when it ends |
| `resume()` | `resume()` | Undo a cancel |
| `redeemPromo(code)` | `redeem_promo(code)` | `trialDays`, `trialCreditCents` and `appliesTo` (`next_checkout` or `current_trial`) |
| `balance()`, `transactions()` | `balance()`, `transactions()` | Prepaid credits and enterprise accounts |
| `paymentMethods()`, `removePaymentMethod(id)` | `payment_methods()`, `remove_payment_method(id)` | Saved cards; add a card in Checkout or on the Billing page |

Checkout and invoices are web pages: the user finishes them in a browser. `startProNow`, `cancel` and `resume` change what the account pays, so call them only on the account owner's request. Nothing in the SDK retries a payment.

When the account has to pay before it can create something, the call raises `PaymentRequiredError` (HTTP 402) with the platform's sentence and the page to open next; see [Errors](sandboxes.md#errors).

## Optional CLI adapter

Native HTTP methods do not need the CLI. `LizardCLI` supports local workflows such as linking a directory or running CLI commands. Install Lizard CLI 4.0.8+ on `PATH` before using it.

See [CLI adapter usage](cli-parity.md#optional-cli-adapter). For config changes, inspect `ConfigApplyError.result` before retrying: the server may have saved the config even if a deploy or restart failed.
