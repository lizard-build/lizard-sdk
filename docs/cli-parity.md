# CLI coverage

Checked against CLI 4.0.8 (`92de61f`) and the backend source at the audit date. The command map in `tests/contracts/cli-coverage.json` lists every discovered command. `scripts/audit_cli.py` fails when the installed CLI adds a command without a mapping.

CLI PR #13 removes `sandbox pause`, `resume`, `fork`, `snapshot`, `restore` and the `snapshot-fork` alias. The updated CLI has 99 command entries. The coverage map keeps these five commands separately as legacy entries so discovery can also check published CLI 4.0.8 until the removal ships. This historical discovery audit predates the Firecracker sandbox runtime; the current SDK supports those operations as described below.

## Native APIs

Both SDKs expose projects, project config, services, deploys, addons, secrets, domains, metrics, workspaces, API keys, regions, billing reads and Checkout, S3 objects, GitHub status and checkout, sandboxes, snapshots and volumes. Python uses snake_case where TypeScript uses camelCase.

| CLI group | SDK entry points |
| --- | --- |
| `project`, `ps`, `config apply` | `projects.list/get/create/update/delete/services/apply` |
| `add`, `up`, `redeploy`, `restart`, `scale`, `port`, `service` | `services.deploy/upload/redeploy/restart/scale/update/get/delete`; `addons.*` |
| `logs`, `events`, `ssh` | `services.logs/history/streamLogs/buildLogs/events/pods/exec`; Python `exec_` |
| `secrets` | `secrets.list/set/delete/refs`; pass parsed dotenv values to `set` |
| `domain` | `domains.info/list/add/generate/verify/delete` |
| `metrics` | `metrics.service/addon/project/cpu/memory/network/disk/all/cost` |
| `git` | `github.status/installUrl/checkout` |
| `s3` | `storage.list/upload` |
| `billing` (formerly `credits`) | `billing.subscription/startCheckout/startProNow/cancel/resume/redeemPromo/balance/transactions/summary/live/paymentMethods/removePaymentMethod` |
| `sandbox` | `Sandbox.create/connect/list/restore/snapshots/deleteSnapshot`; instance `kill/pause/resume/setTimeout/getInfo/getHost/exposePort/unexpose/fork/snapshot/logs`, `fs.*`, `process.*` |
| `volume` | `Volume.*`, project-bound `client.volumes.*`, `projects.volumeLimits` |
| `workspace`, `keys`, `regions`, `whoami` | `workspaces.*`, `apiKeys.*`, `regions.list`, `whoami` |

API methods take explicit IDs. Interactive pickers and directory links belong to the CLI. `services.upload` takes tar.gz bytes; the CLI handles directory packing and `.gitignore`. GitHub App installation and Pro Checkout return a URL the caller opens to finish consent or payment.

## Optional CLI adapter

`LizardCLI` runs the installed CLI with an argument array, without a shell. It returns the exit code, stdout, stderr and parsed JSON events. It supports local workflows such as `init`, `link`, `unlink`, `run`, login/logout, opening docs/dashboard, skill discovery and upgrades. It does not turn a failed exit code into success or add confirmation flags to general commands.

```ts
import { LizardCLI } from '@lizard-build/sdk'
const cli = new LizardCLI({ cwd: '/path/to/app' })
const result = await cli.run(['status'])
if (result.code !== 0) throw new Error(result.stderr || result.stdout)
```

```python
from lizard import LizardCLI
result = LizardCLI(cwd="/path/to/app").run(["status"])
if result.code:
    raise RuntimeError(result.stderr or result.stdout)
```

These are CLI-backed operations, not native HTTP implementations. The CLI must be installed. Native platform methods do not need it.

## Backend limits

Sandbox pause/resume (memory and processes kept), snapshot creation/restoration and fork are supported on Firecracker sandboxes. Both SDKs also expose snapshot get/list/delete and wait helpers, plus warm-pool resizing and pool pause/resume for container snapshots.

Sandbox file upload accepts UTF-8 text. Passing invalid UTF-8 bytes fails locally instead of corrupting data. Use `readBytes` / `read_bytes` for binary downloads.

## Pro billing

Pro replaces prepaid credits. `billing.subscription`, `startCheckout`, `startProNow`, `cancel` and `resume` are new, and `redeemPromo` returns the trial the code gives. `purchase` (card and crypto), `autoTopup`, `setAutoTopup`, `runAutoTopup`, `setupPaymentMethod`, `x402Quote`, `paymentStatus` and `payX402` are removed, with their Python twins: the platform refuses those calls for every account outside the old prepaid credits, and x402 and crypto payments are retired. Python's `redeem_promo` returns a `PromoRedemption` instead of a dict. An HTTP 402 raises `PaymentRequiredError`, a `LizardError` subclass.

## Changes from 0.1.8

- Service config and secret writes use `config:apply`; the removed service PATCH route is no longer called. `services.update` returns the apply result. If config was saved but a deploy/restart action failed, config helpers raise `ConfigApplyError` with the server result; they never retry the saved change. It reads `configRevision` unless the caller supplies a revision or explicitly sets `force`.
- App replicas use PATCH `/scale`; CPU and memory use config apply. Addon resize uses config apply. App storage resizing raises an error before sending a request.
- Upload sends raw tar.gz bytes with query parameters, including `appId`, worker port 0 and pre-deploy commands. It no longer sends multipart form data.
- Exec collects SSE stdout, stderr and the exit event. A truncated stream raises an error. Build log iterators stream build events and propagate errors.
- Service log snapshots query project logs by service name. Live app logs use the SSE endpoint. Domain methods send `hostname` and retain DNS verification fields.
- Metrics use the combined series endpoint. `all` fetches once and returns all six series. Python now accepts `range`, matching TypeScript; obsolete `since`/`until` metric arguments are removed. Cost returns the backend project row (`costUsd`) or null/None, instead of made-up component totals from an absent endpoint.
- Project-name lookup caches per credential and rejects names shared by multiple projects.
- Python accepts sandbox lifetime 0 and imports file/process timeout constants at runtime. Python's supported minimum is 3.10, matching the syntax already used in the package.

## Verification

`tests/contracts/platform.json` contains shared request/response fixtures based on CLI and backend routes. Both test suites invoke the SDK methods, check HTTP method, URL, body, binary payload and credentials, and consume streams. Regression tests cover malformed/truncated streams, UTF-8 chunks, empty responses, project scope, exit codes and argument handling. They use mock HTTP responses; they do not prove deployed backend behavior.

```sh
npm install
npm test
npm run build
npm run lint
PYTHONPATH=packages/python python -m pytest packages/python/tests tests
python scripts/audit_cli.py --output cli-audit.json
```

The historical node-agent tests require `LIZARD_LIVE_TESTS=1` and `ADMIN_SECRET` on an approved test host. They are skipped by default, including tests that create their own sandbox outside shared fixtures. CLI help discovery is reported separately from functional calls. Payment, DNS and destructive live tests need an approved environment and budget.
