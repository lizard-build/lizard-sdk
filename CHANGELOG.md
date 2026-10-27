# Changelog

This repository ships Lizard SDK as `@lizard-build/sdk` on npm and `lizard-sdk` on PyPI. Both packages share one version number. Every push to `main` publishes a patch release, so most releases change docs or fix one bug. This file lists the changes that matter to code that uses the SDK.

From 1.0.0 the SDK follows [semantic versioning](https://semver.org): a change that breaks a documented method, option or return type ships only in a new major version.

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
