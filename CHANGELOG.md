# Changelog

This repository ships Lizard SDK as `@lizard-build/sdk` on npm and `lizard-sdk` on PyPI. Both packages share one version number. Every push to `main` publishes a patch release, so most releases change docs or fix one bug. This file lists the changes that matter to code that uses the SDK.

From 1.0.0 the SDK follows [semantic versioning](https://semver.org): a change that breaks a documented method, option or return type ships only in a new major version.

## Unreleased

- Docs: sandbox start limits per tier (per day 100 on the trial, 400 on Pro, 1,000 on Pro 5x, 3,000 on Pro 20x; per minute and per hour too). No code change.
- Pro has three tiers: Pro ($19/month), Pro 5x ($99) and Pro 20x ($499). `billing.subscription()` returns `tier`, `pendingTier` and `tiers` (Python: `tier`, `pending_tier`, `tiers` as `ProTierOption`). `billing.startCheckout({ tier })` opens Checkout for Pro 5x or Pro 20x, and the new `billing.changeTier(tier)` / `change_tier(tier)` moves a paid subscription between tiers. Moving up is charged now, prorated. Moving down starts with the next period.
- Account sandbox limits count vCPU of running sandboxes (Small 2, Medium 4, Large 8). On `SANDBOX_LIMIT_REACHED`, `LimitExceededError` now has `unit` (`vcpu` or `sandboxes`), `needed` (the vCPU the refused sandbox needs) and `tier`. `limit` and `running` are in `unit`, so in vCPU they count vCPU, not sandboxes.
- `Sandbox.create()` with no `region`, volume or snapshot now asks for `us-east-1`. It used to leave the choice to the platform, which also picked `us-east-1`. With a volume or snapshot, the sandbox still starts in their region. If new sandboxes in `us-east-1` are paused (503 `region_unavailable`), the SDK asks once more without a region and the platform picks an open one. A `region` you pass is never swapped for another.

## 1.0.0 (2026-10-27)

First stable release. The API is the same as in 0.1.83: code that runs on 0.1.83 runs on 1.0.0.

- `new Lizard({ project }).create(template)` / `Lizard(project=...).create(template)` and `Sandbox.create(template, { project })` / `Sandbox.create(template, project=...)` send the same request, and both are stable. Every README example now uses the client.
- The PyPI package is marked `Development Status :: 5 - Production/Stable`.

## Before 1.0

Releases 0.1.1 to 0.1.83 came out between June 24 and October 27, 2026. These changed how code calls the SDK:

- **0.1.11 (2026-07-21).** Examples stopped using the template names `node22` and `python312`, which the platform never had. Current templates are `base`, `interpreter` and `desktop`.
- **0.1.18, 0.1.19 (2026-07-23).** `Sandbox.create()` needs a project: `projectId` in TypeScript, `project_id` in Python.
- **0.1.21 (2026-07-27).** New `Lizard` client pinned to one project. The new `project` option takes a project's ID, slug or name; `projectId` / `project_id` still work.
- **0.1.40 (2026-09-29).** The platform API moved to the routes the CLI uses: service config and secrets go through `config:apply`, uploads send a raw tar.gz, and Python metrics take `range` instead of `since` / `until`. See [CLI coverage and migration](docs/cli-parity.md#changes-from-018).
- **0.1.51 (2026-10-05).** `CodeSandbox` starts the `interpreter` template and runs code over `exec`; it no longer expects a server on port 8080, and the `code-interpreter-v1` template is gone. `ProcessInfo.cmd` is a string array, and `fork()` returns a typed `ForkResult` instead of raw JSON.
- **0.1.52 (2026-10-05).** Billing methods follow Lizard Pro. Removed: `purchase`, `autoTopup`, `setAutoTopup`, `runAutoTopup`, `setupPaymentMethod`, `x402Quote`, `paymentStatus` and `payX402`, with their Python twins. Python's `redeem_promo` returns a `PromoRedemption` instead of a dict.
- **0.1.78 (2026-10-21).** Lizard Git serves no git protocol. `cloneUrl` is deprecated and its address answers 410; send changes with `commitFiles`.
