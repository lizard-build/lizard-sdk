# Lizard SDK

[![npm](https://img.shields.io/npm/v/@lizard-build/sdk)](https://www.npmjs.com/package/@lizard-build/sdk)
[![PyPI](https://img.shields.io/pypi/v/lizard-sdk)](https://pypi.org/project/lizard-sdk/)
[![Checks](https://github.com/lizard-build/lizard-sdk/actions/workflows/test.yml/badge.svg)](https://github.com/lizard-build/lizard-sdk/actions)

Lizard (lizard.build) provides cloud sandboxes for AI agents and code execution. Lizard SDK provides the official TypeScript, JavaScript and Python clients for creating and controlling Lizard Sandboxes.

Run AI-generated Python in a stateful code interpreter, execute shell commands, read and write files, or control a browser and desktop. Each sandbox runs as a Firecracker microVM with its own kernel.

[TypeScript guide](https://github.com/lizard-build/lizard-sdk/blob/main/packages/js/README.md) · [Python guide](https://github.com/lizard-build/lizard-sdk/blob/main/packages/python/README.md) · [Sandbox reference](https://github.com/lizard-build/lizard-sdk/blob/main/docs/sandboxes.md) · [Platform guide](https://github.com/lizard-build/lizard-sdk/blob/main/docs/platform.md)

## Use cases

- Execute AI-generated code with a [stateful Python code interpreter](https://lizard.build/docs/sandboxes/code-interpreter/).
- Run coding agents such as [Claude Code](https://lizard.build/docs/sandboxes/guides/claude-code/) in a cloud sandbox.
- Automate a browser or desktop with [screenshots, clicks and keyboard input](https://github.com/lizard-build/lizard-sdk/blob/main/docs/sandboxes.md#desktop-computer-use).
- Open an agent's dev server through a [private preview URL](https://lizard.build/docs/sandboxes/preview-urls/).

## Install

| SDK | Install | Requires |
| --- | --- | --- |
| TypeScript / JavaScript | `npm install @lizard-build/sdk` | Node.js 18+ |
| Python | `pip install lizard-sdk` | Python 3.10+ |

## Quickstart

Start with Lizard Pro or its trial; see [billing and trial terms](https://lizard.build/docs/platform/billing/). Create an API key and project at [lizard.build](https://lizard.build). Set your key in the environment and replace `my-project` below with your project's ID, slug or unique name.

```sh
export LIZARD_API_KEY="your-api-key"
```

### TypeScript

```ts
import { Lizard } from '@lizard-build/sdk'

const lizard = new Lizard({ project: 'my-project' })
const sandbox = await lizard.create('base', { timeoutMs: 300_000 })

try {
  await sandbox.fs.write('/tmp/hello.txt', 'Hello from Lizard!')
  const result = await sandbox.process.exec('cat /tmp/hello.txt')
  if (result.exitCode !== 0) throw new Error(result.stderr)
  console.log(result.stdout)
} finally {
  await sandbox.kill()
}
```

Use an ESM file with top-level `await`, or put the code in an async function. The [TypeScript guide](https://github.com/lizard-build/lizard-sdk/blob/main/packages/js/README.md) includes a run command.

### Python

```python
from lizard import Lizard

lizard = Lizard(project="my-project")

with lizard.create("base", timeout_ms=300_000) as sandbox:
    sandbox.fs.write("/tmp/hello.txt", "Hello from Lizard!")
    result = sandbox.process.exec_("cat /tmp/hello.txt")
    if result.exit_code != 0:
        raise RuntimeError(result.stderr)
    print(result.stdout)
```

The Python context manager kills the sandbox when the block ends, including when it raises an error. TypeScript uses `try/finally` for the same cleanup.

## Run code with state (CodeSandbox)

`CodeSandbox` boots the `interpreter` template and runs Python in a persistent Jupyter kernel inside the sandbox: variables survive between calls, the value of the last expression and matplotlib charts come back in `results`, and exceptions in `error`.

```ts
import { CodeSandbox } from '@lizard-build/sdk'

const sandbox = await CodeSandbox.create({ project: 'my-project', timeoutMs: 300_000 })
try {
  const setup = await sandbox.runCode('x = 21')
  if (setup.error) throw setup.error
  const run = await sandbox.runCode('x * 2')
  if (run.error) throw run.error
  const out = run.results[0]
  if (out?.type === 'result') console.log(out.data) // "42"
} finally {
  await sandbox.kill()
}
```

```python
from lizard import CodeSandbox

with CodeSandbox.create(project="my-project", timeout_ms=300_000) as sandbox:
    setup = sandbox.run_code("x = 21")
    if setup.error:
        raise RuntimeError(f"{setup.error.name}: {setup.error.message}")
    run = sandbox.run_code("x * 2")
    if run.error:
        raise RuntimeError(f"{run.error.name}: {run.error.message}")
    print(run.results[0].data)  # "42"
```

JavaScript and Bash execution starts a fresh process on each call, with no shared state. The `interpreter` template ships Node 22. Shell commands through `process.exec()` / `process.exec_()` also start separate processes and return stdout, stderr and an exit code. See the [code interpreter guide](https://lizard.build/docs/sandboxes/code-interpreter/).

## Account, pricing and machine size

Lizard Pro costs $19 a month, taxes included, with $19 of usage each month. Unused usage does not carry over. Usage above that amount is pay as you go at the published rates. New accounts can start a 7-day trial with $5 of usage; a card is required, and nothing is charged until the trial ends. If trial usage runs out, workloads pause until Pro starts. See the current [billing and trial terms](https://lizard.build/docs/platform/billing/).

Sandbox rates below were checked on October 23, 2026. See [current sizes and prices](https://lizard.build/docs/platform/limits/#sandbox-sizes) before estimating costs.

Sandboxes come in three sizes: `small` (2 vCPU / 4 GB, $0.0162/h), `medium` (4 vCPU / 8 GB, $0.0324/h, the default) and `large` (8 vCPU / 16 GB, $0.0648/h). Billing is flat by size, per second while the sandbox runs, including idle time. CPU and RAM are included. The sandbox egress allowance is [2 TB per account over a rolling 30 days](https://lizard.build/docs/platform/limits/#sandbox-egress), with no separate per-GB charge. A successful pause stops compute charges; storage in Persistent Volumes is billed separately, including while paused.

Pass `{ size: 'large' }` in TypeScript or `size="large"` in Python when creating a sandbox. See the package guides for examples that clean up when the task ends.

## What you can do

| Task | TypeScript | Python |
| --- | --- | --- |
| Run a shell command | `sandbox.process.exec(cmd)` | `sandbox.process.exec_(cmd)` |
| Read or write a file | `sandbox.fs.read(path)` / `write(path, text)` | Same method names |
| Run code with state between calls | `codeSandbox.runCode(code)` | `code_sandbox.run_code(code)` |
| Expose an HTTP port (private, token-gated) | `sandbox.exposePort(port)` / `getHost(port)` | `sandbox.expose_port(port)` / `get_host(port)` |
| Pause, snapshot, restore, fork | `pause()`, `snapshot()`, `Sandbox.restore(id)`, `fork()` | Same method names |
| Drive a desktop (computer use) | `sandbox.desktop.start()`, `screenshot()`, `click()`, `type()` | Same on `sandbox.desktop` |
| Reconnect to a running sandbox | `Sandbox.connect(id)` | `Sandbox.connect(id)` |
| Keep files across sessions | `lizard.volumes.getOrCreate(name)` | `lizard.volumes.get_or_create(name)` |
| Manage cloud apps | `lizard.services`, `projects`, `addons` | Same namespaces |
| Cap a workspace: sandboxes at once, CPU/RAM its services use | `lizard.workspaces.setLimits(id, { maxRunningSandboxes: 5, maxCpuVcpus: 2 })` | `lizard.workspaces.set_limits(id, max_running_sandboxes=5, max_cpu_vcpus=2)` |
| Show your own prices to a workspace's scoped keys (resellers) | `lizard.workspaces.setResalePricing(id, { cpu: 4, sandbox: 4 })` | `lizard.workspaces.set_resale_pricing(id, cpu=4, sandbox=4)` |
| Pause an app, database, project or workspace (keeps URLs, passwords, data) | `lizard.services.pause(id)`, `addons.pause(projectId, id)`, `projects.pause(id)`, `workspaces.pause(id)`; `resume` likewise | Same method names |
| Make an app or database serverless (sleep when idle, ~1 s wake) | `lizard.services.setSleep(id, { enabled: true, idleMinutes: 15 })`, `addons.setSleep(projectId, id, …)`; `getSleep` reads it | `set_sleep(id, enabled=True, idle_minutes=15)`, `get_sleep` |

See the [sandbox reference](https://github.com/lizard-build/lizard-sdk/blob/main/docs/sandboxes.md) for configuration, streaming, ports, volumes, errors and method names in both languages.

## Desktop (computer use)

Create a sandbox from the `desktop` template, call `await sandbox.desktop.start()` in TypeScript or `sandbox.desktop.start()` in Python, and open the returned `url` in a browser to watch and control it. Agents drive it with `screenshot()`, `click(x, y)`, `type(text)` and `press('ctrl+l')`. The URLs are secrets: `url` gives full control, `viewOnlyUrl` / `view_only_url` only watches. See the [desktop guide](https://github.com/lizard-build/lizard-sdk/blob/main/docs/sandboxes.md#desktop-computer-use).

## Runtime and persistence

Lizard Sandboxes run as Firecracker microVMs, each with its own kernel. Use Persistent Volumes mounted at `/workspace` to keep files after a sandbox ends.

- `pause()` / `resume()` keep the sandbox's memory and running processes.
- `snapshot()` saves a running sandbox (memory, processes and files) and is ready in about 2 s; `Sandbox.restore()` starts a copy in about 0.4 s.
- `fork()` clones a running sandbox, processes and all.

See the [snapshot guide](https://github.com/lizard-build/lizard-sdk/blob/main/docs/sandboxes.md#pause-resume-snapshots-and-fork). File watching and sandbox log streaming are not available yet. A volume can grow but not shrink, and a sandbox with a volume attached cannot be forked.

The SDK and CLI default to a five-minute lifetime. The raw API and dashboard default to no expiration. Set `timeoutMs: 0` in TypeScript or `timeout_ms=0` in Python at creation to disable expiration. Commands do not reset the deadline. See [current runtime limits](https://lizard.build/docs/sandboxes/).

## Versions and API stability

Lizard SDK follows [semantic versioning](https://semver.org) from 1.0.0. A change that breaks a documented method, option or return type ships only in a new major version. New features come in minor versions, fixes in patch versions. The npm and PyPI packages share one version number. The [changelog](https://github.com/lizard-build/lizard-sdk/blob/main/CHANGELOG.md) lists what changed, including the API changes made before 1.0.

There are two ways to create a sandbox, and both are stable:

| | TypeScript | Python |
| --- | --- | --- |
| Client pinned to a project | `new Lizard({ project }).create(template)` | `Lizard(project=...).create(template)` |
| Class method | `Sandbox.create(template, { project })` | `Sandbox.create(template, project=...)` |

The client passes its project to `Sandbox.create()`, so both send the same request. The examples use the client because it also reaches volumes and the platform API. `CodeSandbox.create()` takes the project the same way as `Sandbox.create()`.

Platform facts such as prices, limits and templates can change without a new SDK version. See [current limits](https://lizard.build/docs/sandboxes/).

## Other SDK capabilities

The SDK also manages apps, Managed Postgres, Managed Redis, Managed Object Storage and projects. See the [platform guide](https://github.com/lizard-build/lizard-sdk/blob/main/docs/platform.md).

## Documentation

- [Sandboxes overview and current limits](https://lizard.build/docs/sandboxes/).
- [Sandboxes quickstart](https://lizard.build/docs/sandboxes/quickstart/).
- [Billing and trial terms](https://lizard.build/docs/platform/billing/).
- [TypeScript guide](https://github.com/lizard-build/lizard-sdk/blob/main/packages/js/README.md) and [Python guide](https://github.com/lizard-build/lizard-sdk/blob/main/packages/python/README.md): setup and runnable examples.
- [Sandbox reference](https://github.com/lizard-build/lizard-sdk/blob/main/docs/sandboxes.md): commands, files, code, ports, lifecycle, snapshots, fork and persistence.
- [Platform guide](https://github.com/lizard-build/lizard-sdk/blob/main/docs/platform.md): projects, workspaces, scoped keys and cloud services.
- [CLI coverage and migration](https://github.com/lizard-build/lizard-sdk/blob/main/docs/cli-parity.md): native APIs, optional CLI adapter and backend limits.
- [Changelog](https://github.com/lizard-build/lizard-sdk/blob/main/CHANGELOG.md): what changed in each release, including the API changes made before 1.0.
- [Contributing](https://github.com/lizard-build/lizard-sdk/blob/main/CONTRIBUTING.md): local checks and test scope.

## License

[Apache-2.0](https://github.com/lizard-build/lizard-sdk/blob/main/LICENSE)
