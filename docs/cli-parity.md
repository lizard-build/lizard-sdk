# CLI coverage

Checked against CLI 4.0.77 (`53c2076`). The command map in `tests/contracts/cli-coverage.json` lists every discovered command: the SDK methods that cover it, or `LizardCLI.run` with the reason only the CLI can do it. `scripts/audit_cli.py` fails when the installed CLI is another version, adds a command without a mapping or drops a mapped one.

CLI 4.0.77 has 265 command entries. New since the 4.0.24 map: Lizard Git (`git` repositories, issues, pull requests, CI and working copies), `domain list`, `domain owned` and `domain dns` for domains bought on Lizard (lizard.build), `pause`, `resume`, `sleep`, project and workspace pause and resume, workspace limits and resale prices, `s3 url` and `sandbox snapshot-scope`. `sandbox pause`, `resume`, `fork`, `snapshot` and `restore` are regular commands again, so the map no longer keeps them as legacy entries; the legacy `credits` rows are gone too. `sandbox logs` is gone. `sandbox snapshot-pause`, `snapshot-resume` and `snapshot-warm` still run but are hidden from help, since they act only on older snapshots, so the map leaves them out; the SDK keeps `Sandbox.pauseSnapshot`, `resumeSnapshot` and `setSnapshotWarmPool` for them.

## Native APIs

Both SDKs expose projects, project config, services, deploys, addons, secrets, domains, metrics, workspaces, API keys, regions, billing reads and Checkout, S3 objects, GitHub status and checkout, Lizard Git, sandboxes, snapshots and volumes. Python uses snake_case where TypeScript uses camelCase.

| CLI group | SDK entry points |
| --- | --- |
| `project`, `ps`, `config apply` | `projects.list/get/create/update/delete/services/apply/pause/resume` |
| `add`, `up`, `redeploy`, `restart`, `pause`, `resume`, `sleep`, `scale`, `port`, `service` | `services.deploy/upload/redeploy/restart/pause/resume/getSleep/setSleep/scale/update/get/delete`; `addons.*` (incl. `addons.pause/resume/getSleep/setSleep`) |
| `logs`, `events`, `ssh` | `services.logs/history/streamLogs/buildLogs/events/pods/exec`; Python `exec_` |
| `secrets` | `secrets.list/set/delete/refs`; pass parsed dotenv values to `set` |
| `domain` | `domains.info/list/add/generate/verify/delete`; `domain owned` and `domain dns` (domains bought on Lizard) have no SDK method |
| `metrics` | `metrics.service/addon/project/cpu/memory/network/disk/all/cost` |
| `git connect`, `git checkout`, `git status` (outside a working copy) | `github.status/installUrl/checkout` |
| `git` (Lizard Git) | `git.repos/issues/pulls/actions/environments/collaborators/webhooks/branchRules/labels/releases/statuses/notifications/tokens`, `git.me`; working copies (`git clone`, `init`, `status`, `diff`, `commit`, `push`, `uncommit`, `sync`, `switch`, `sparse`, `pr checkout`) are CLI-only |
| `s3` | `storage.list/upload`; `s3 url` signs the link in the CLI and has no SDK method |
| `billing` (formerly `credits`) | `billing.subscription/startCheckout/startProNow/cancel/resume/redeemPromo/balance/transactions/summary/live/paymentMethods/removePaymentMethod` |
| `sandbox` | `Sandbox.create/connect/list/restore/snapshots/mySnapshots/setSnapshotScope/deleteSnapshot`; instance `kill/pause/resume/setTimeout/getInfo/getHost/exposePort/unexpose/fork/snapshot/logs`, `fs.*`, `process.*` |
| `volume` | `Volume.*`, project-bound `client.volumes.*`, `projects.volumeLimits` |
| `workspace`, `keys`, `regions`, `whoami` | `workspaces.*`, `apiKeys.*`, `regions.list`, `whoami` |

API methods take explicit IDs. Interactive pickers and directory links belong to the CLI. `services.upload` takes tar.gz bytes; the CLI handles directory packing and `.gitignore`. GitHub App installation and Pro Checkout return a URL the caller opens to finish consent or payment.

## Optional CLI adapter

`LizardCLI` runs the installed CLI with an argument array, without a shell. It returns the exit code, stdout, stderr and parsed JSON events. It supports local workflows such as `init`, `link`, `unlink`, `run`, login/logout, opening docs/dashboard, skill discovery, upgrades and Lizard Git working copies (`git clone`, `commit`, `push`, `sync`). It does not turn a failed exit code into success or add confirmation flags to general commands.

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

Sandbox pause/resume (memory and processes kept), snapshot creation/restoration and fork are supported on Firecracker sandboxes. Both SDKs also expose snapshot get/list/delete and wait helpers, plus warm-pool resizing and pool pause/resume for older snapshots.

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
