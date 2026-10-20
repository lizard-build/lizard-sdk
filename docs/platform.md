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
| `projects` | `projects` | Projects, config, services and project logs; pause/resume a whole project |
| `services` | `services` | Deploy, inspect, scale, pause/resume, make serverless (sleep when idle) and run commands in apps |
| `addons` | `addons` | Managed databases and other addons (pause/resume, serverless) |
| `secrets` | `secrets` | Environment variables and secret references |
| `domains` | `domains` | App domains and DNS verification |
| `storage` | `storage` | S3 object listing and uploads |
| `github` | `github` | GitHub connection status and checkout |
| `metrics` | `metrics` | Resource use and project costs |
| `workspaces` | `workspaces` | Workspaces and resource ownership; pause/resume a whole workspace (owner); resale prices for its scoped keys (owner) |
| `apiKeys` | `api_keys` | API keys and scopes |
| `regions` | `regions` | Available regions |
| `billing` | `billing` | The account's plan, Pro Checkout, promo codes, balance and transactions |
| `volumes` | `volumes` | Persistent files for sandboxes in the client's project |
| `git` | `git` | Lizard Git: repositories, issues, pull requests, reviews, CI runs, releases, webhooks, branch rules ([below](#lizard-git)) |

`whoami()` returns the account identity visible to the credential. `platform` exposes the underlying HTTP client for endpoints without a dedicated method. See [CLI coverage](cli-parity.md#native-apis) for the method map.

## Workspaces and scoped keys

For an application with separate users, you can create a workspace and project for each user, then issue a key scoped to that workspace. Run this from your trusted application server with a key that has no scopes.

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

A key with no scopes has access to all resources the creating account can reach. Pass `workspaces` or `projects` to limit that access. Scoped keys cannot create broader keys. Creating a workspace needs a key with no scopes; a scoped key gets HTTP 403 with `code: 'ACCOUNT_SCOPE_REQUIRED'`. A scoped key can create projects only in a workspace it covers; anywhere else it gets HTTP 403 with `code: 'PROJECT_OUT_OF_SCOPE'`.

If tools inside a sandbox need Lizard access, pass a scoped key through `lizardToken` / `lizard_token`. Any code in that sandbox can read the key and use its permissions. Choose a template with the CLI installed when running CLI commands.

### Account and billing access

### Resale prices

If you resell Lizard, for example through your own tool running in a sandbox with a key scoped to a user's workspace, you can show that user your prices instead of Lizard's. Set a multiplier from 1 to 100 per resource on the workspace. Every key scoped to it, or to one of its projects, then sees prices and costs multiplied: sandbox prices, `metrics` costs and billing summaries. Your own dashboard, keys with no scopes and what Lizard bills you are unchanged.

```ts
await lizard.workspaces.setResalePricing(workspace.id, { cpu: 4, memory: 4, sandbox: 4 })
await lizard.workspaces.getResalePricing(workspace.id)   // { enabled, multipliers }
await lizard.workspaces.clearResalePricing(workspace.id)
```

```python
lizard.workspaces.set_resale_pricing(workspace.id, cpu=4, memory=4, sandbox=4)
lizard.workspaces.get_resale_pricing(workspace.id)
lizard.workspaces.clear_resale_pricing(workspace.id)
```

Resources are `cpu`, `memory`, `storage` (volumes), `egress`, `objectStorage` (`object_storage` in Python) and `sandbox`. A set call replaces them all; a resource left out is 1. Only the workspace owner can read or change them, with a key that has no scopes: a scoped key gets HTTP 403 with `ACCOUNT_SCOPE_REQUIRED`. A key with resale prices also gets that 403 from the workspace's billing account, whose plan and Stripe figures are Lizard's.

### Workspace limits

Cap what one workspace (for example one customer's) may run at once, whoever starts the work:

```ts
await lizard.workspaces.setLimits(workspace.id, { maxRunningSandboxes: 5, maxCpuVcpus: 2, maxMemoryMb: 4096, maxDiskGb: 20 })
const { limits, usage } = await lizard.workspaces.getLimits(workspace.id)  // usage: runningSandboxes, cpuVcpus, memoryMb
```

```python
lizard.workspaces.set_limits(workspace.id, max_running_sandboxes=5, max_cpu_vcpus=2, max_memory_mb=4096, max_disk_gb=20)
info = lizard.workspaces.get_limits(workspace.id)  # info.running_sandboxes, info.cpu_vcpus, info.memory_mb
```

- `maxRunningSandboxes`: sandboxes running or resuming at once (paused ones are free). A create, fork or resume past it fails with HTTP 429 `WORKSPACE_SANDBOX_LIMIT`.
- `maxCpuVcpus`, `maxMemoryMb`: what the workspace's apps and databases **use**, measured every ~10 seconds across regions, not their configured sizes. Memory is the working set: what the processes hold, without the file cache the kernel frees on demand (a database that has read a lot of data is not counted for its cache). While usage is at or over a cap, deploys, redeploys, restarts, scale-ups, new databases and resumes there fail with HTTP 429 `WORKSPACE_USAGE_LIMIT`. Services already running keep running.
- `maxDiskGb`: the SSD the workspace's databases and volumes **hold** (data written, measured; not the sizes they were created with). While at or over it, new volumes, volume growth, new databases and template deploys fail with HTTP 429 `WORKSPACE_USAGE_LIMIT`; data already written stays. A sandbox's own `/workspace` disk is not counted.

A field you leave out stays as it is; `null` (`None`) removes that limit. Only the owner sets limits, with a key that has no scopes. Anyone in the workspace can read them with the current usage, including a key scoped to it.

Billing belongs to the account, across all its workspaces. Scoped keys cannot access account billing or account-wide usage; those routes return HTTP 403 with `ACCOUNT_SCOPE_REQUIRED`. The one exception is `billing.subscription({ workspaceId })` / `billing.subscription(workspace_id=...)`, which any member's key that reaches the workspace can call to see why the owner's account is blocked; it leaves out the card and invoice. A scoped key must pass the workspace (without it, `ACCOUNT_SCOPE_REQUIRED`), and in a workspace with resale prices it gets `ACCOUNT_SCOPE_REQUIRED` too: the owner's plan and credits are at Lizard's prices. A scoped key's `whoami()` response never names the account: it carries only `scoped: true` and the key's `scopes`, each project or workspace with its name -- no id, username, email, balance or plan. Use scoped `metrics` calls for project costs.

`workspaces.delete()` requires an empty workspace by default. The `force` option deletes the workspace with its apps, addons and projects, but not its sandboxes, sandbox volumes or snapshots: a running sandbox keeps running with no workspace left to find it in. Kill the workspace's sandboxes and delete its volumes and snapshots before you pass `force`. Revoking a key or deleting a resource takes effect immediately.

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

## Lizard Git

`git` reaches [Lizard Git](https://git.lizard.build) with the same key. The key must have no scopes: Lizard Git refuses scoped keys, because they don't say which repositories they may reach. For a key limited to some repositories, refs, paths or read-only access, mint a Lizard Git token with `git.tokens.create` and pass it as `apiKey`. The SDK reads `LIZARD_GIT_URL` (default `https://git.lizard.build`), or pass `gitUrl` / `git_url`.

Repositories are named `"owner/name"`.

| Group | What it does |
| --- | --- |
| `git.repos` | Create, list, update, delete, star, fork; refs, branches, tree, files, file contents, raw bytes, search, commits, compare, archive; `commitFiles` / `commit_files` (commit on the server, with `expect` for compare-and-swap and an idempotency key), `land` (rebase a branch onto another on the server), `reflog`, `cloneUrl` / `clone_url` |
| `git.issues` | Create, list (state, text, label, assignee), get with comments, update labels and assignees, comment, close, reopen |
| `git.pulls` | The same, plus create (draft, from a fork, reviewers), `ready`, `merge` (merge, squash, rebase; delete the branch), diff, commits, reviews, `review` / `approve` / `requestChanges` with line comments, `checks` (the combined status of the head commit) |
| `git.actions` | Runs (filter by branch, commit, workflow, status, pull request), one run, `wait`, `cancel`, `rerun`, `approve` (a fork's run), job logs (`log` from an offset, `fullLog`, `followLog`), artifacts, workflows, `dispatch` with inputs; `git.actions.secrets` set, list, delete |
| `git.collaborators` | List, invite (read, write, admin), change role, remove, cancel an invitation; your invitations, accept, decline |
| `git.webhooks` | GitHub-style webhooks: create, update, delete, ping, deliveries, redeliver |
| `git.branchRules` / `git.branch_rules` | Protect branches: pull request required, approvals, required checks, block force pushes and deletion, include admins, code owners |
| `git.labels`, `git.releases`, `git.statuses` | Labels; releases with assets; commit statuses (what required checks wait for) |
| `git.notifications`, `git.tokens` | Your notifications (list, mark read); Lizard Git tokens |
| `git.environments`, `git.actions.variables` | Environments (`set` reviewers, preventSelfReview, waitMinutes, branchPolicy/branches; `setSecret`, `variables(env)`); repository variables (`vars.NAME`); a run's `actions.deployments` and `actions.reviewDeployments` (approve/reject) |

```ts
const lizard = new Lizard()
await lizard.git.repos.create({ name: 'app', private: true, readme: true })
await lizard.git.repos.commitFiles('me/app', {
  branch: 'main', message: 'Add CI',
  files: [{ path: '.lizard/workflows/ci.yml', content: 'on: push\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo hi\n' }],
})
const { runs } = await lizard.git.actions.runs('me/app')
const run = await lizard.git.actions.wait('me/app', runs[0].number)
console.log(run.status, await lizard.git.actions.fullLog('me/app', run.jobs[0].id))
```

```python
lizard = Lizard()
pr = lizard.git.pulls.create("me/app", title="Fix", head="fix", base="main", draft=True)
lizard.git.pulls.ready("me/app", pr["number"])
lizard.git.pulls.merge("me/app", pr["number"], method="squash", delete_branch=True)
```

To use plain `git`, clone with `git.repos.cloneUrl(repo, { withKey: true })` (the URL carries the key; keep it out of logs), or set up the CLI's credential helper with `lizard git setup`.

## Optional CLI adapter

Native HTTP methods do not need the CLI. `LizardCLI` supports local workflows such as linking a directory or running CLI commands. Install Lizard CLI 4.0.8+ on `PATH` before using it.

See [CLI adapter usage](cli-parity.md#optional-cli-adapter). For config changes, inspect `ConfigApplyError.result` before retrying: the server may have saved the config even if a deploy or restart failed.
