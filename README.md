# Lizard SDK

[![npm](https://img.shields.io/npm/v/@lizard-build/sdk)](https://www.npmjs.com/package/@lizard-build/sdk)
[![PyPI](https://img.shields.io/pypi/v/lizard-sdk)](https://pypi.org/project/lizard-sdk/)
[![Checks](https://github.com/lizard-build/lizard-sdk/actions/workflows/test.yml/badge.svg)](https://github.com/lizard-build/lizard-sdk/actions)

**Run code, work with files, and build AI agents in Linux sandboxes on Kubernetes.**

Lizard (lizard.build) provides TypeScript and Python SDKs for sandboxes and the cloud services around them: apps, databases, storage, projects and API keys.

[TypeScript guide](https://github.com/lizard-build/lizard-sdk/blob/main/packages/js/README.md) · [Python guide](https://github.com/lizard-build/lizard-sdk/blob/main/packages/python/README.md) · [Sandbox reference](https://github.com/lizard-build/lizard-sdk/blob/main/docs/sandboxes.md) · [Platform guide](https://github.com/lizard-build/lizard-sdk/blob/main/docs/platform.md)

## Install

| SDK | Install | Requires |
| --- | --- | --- |
| TypeScript / JavaScript | `npm install @lizard-build/sdk` | Node.js 18+ |
| Python | `pip install lizard-sdk` | Python 3.10+ |

## Quickstart

Create an account, API key and project at [lizard.build](https://lizard.build). Set your key in the environment and replace `my-project` below with your project's ID, slug or unique name.

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

## Machine size

Sandboxes come in three sizes: `small` (2 vCPU / 4 GB, $0.009/h), `medium` (4 vCPU / 8 GB, $0.018/h, the default) and `large` (8 vCPU / 16 GB, $0.036/h). Billing is flat by size, per second while the sandbox runs; measured CPU/RAM are not charged, egress is free, and volumes bill separately.

```ts
const sandbox = await lizard.create('base', { size: 'large' })
```

```python
sandbox = lizard.create("base", size="large")
```

## Run Python

Run Python with the `interpreter` template. Each process command starts a separate Python process, so Python variables do not survive between calls. Save intermediate results to files. The API returns stdout, stderr, and an exit code; it does not return typed notebook results or chart objects.

```ts
import { Sandbox } from '@lizard-build/sdk';

const sandbox = await Sandbox.create('interpreter', {
  projectId: 'proj_123', timeoutMs: 300_000,
});
try {
  const result = await sandbox.process.exec("python -c 'print(2 ** 10)'");
  console.log(result.stdout, result.stderr, result.exitCode);
} finally {
  await sandbox.kill();
}
```

```python
from lizard import Sandbox

sandbox = Sandbox.create("interpreter", project_id="proj_123", timeout_ms=300_000)
try:
    result = sandbox.process.exec_("python -c 'print(2 ** 10)'")
    print(result.stdout, result.stderr, result.exit_code)
finally:
    sandbox.kill()
```

`CodeSandbox`, `runCode` / `run_code`, and execution-context methods remain in the SDK, but the hosted template catalog does not provide their required execution server. The legacy default `code-interpreter-v1` is unavailable. Changing its name to `interpreter` does not enable this API. Use `Sandbox.create("interpreter")` and process commands as shown below.

## What you can do

| Task | TypeScript | Python |
| --- | --- | --- |
| Run a shell command | `sandbox.process.exec(cmd)` | `sandbox.process.exec_(cmd)` |
| Read or write a file | `sandbox.fs.read(path)` / `write(path, text)` | Same method names |
| Expose an HTTP port | `sandbox.getHost(port)` | `sandbox.get_host(port)` |
| Drive a desktop (computer use) | `sandbox.desktop.start()`, `screenshot()`, `click()`, `type()` | Same on `sandbox.desktop` |
| Reconnect to a running sandbox | `Sandbox.connect(id)` | `Sandbox.connect(id)` |
| Keep files across sessions | `lizard.volumes.getOrCreate(name)` | `lizard.volumes.get_or_create(name)` |
| Resize a volume in place | `lizard.volumes.resize(name, sizeGb)` | `lizard.volumes.resize(name, size_gb)` |
| Manage cloud apps | `lizard.services`, `projects`, `addons` | Same namespaces |

See the [sandbox reference](https://github.com/lizard-build/lizard-sdk/blob/main/docs/sandboxes.md) for configuration, streaming, ports, volumes, errors and method names in both languages.

## Desktop (computer use)

Create a sandbox from the `desktop` template, call `await sandbox.desktop.start()` and open the returned `url` in a browser to watch and control it. Agents drive it with `screenshot()`, `click(x, y)`, `type(text)` and `press('ctrl+l')`. The URLs are secrets: `url` gives full control, `viewOnlyUrl` / `view_only_url` only watches. See the [desktop guide](docs/sandboxes.md#desktop-computer-use).

## Runtime and persistence

Sandboxes run on **Kubernetes with runc and share the host kernel**. Files outside an attached persistent volume last only for the sandbox's lifetime. Mount a volume at `/workspace` to keep files across sessions. A volume preserves files; it does not preserve running processes or memory.

The Kubernetes backend supports **CRIU pause/resume and private warm snapshots**. Capture running memory and workspace files, keep five copies warm by default, and pause a snapshot pool to release idle compute. See the [snapshot lifecycle guide](docs/sandboxes.md#snapshots-and-criu-pause-resume). `fork()` and file watching remain unsupported.

## Documentation

- [TypeScript guide](https://github.com/lizard-build/lizard-sdk/blob/main/packages/js/README.md) and [Python guide](https://github.com/lizard-build/lizard-sdk/blob/main/packages/python/README.md): setup and runnable examples.
- [Sandbox reference](https://github.com/lizard-build/lizard-sdk/blob/main/docs/sandboxes.md): commands, files, code, ports, lifecycle and persistence.
- [Platform guide](https://github.com/lizard-build/lizard-sdk/blob/main/docs/platform.md): projects, workspaces, scoped keys and cloud services.
- [CLI coverage and migration](https://github.com/lizard-build/lizard-sdk/blob/main/docs/cli-parity.md): native APIs, optional CLI adapter and backend limits.
- [Contributing](https://github.com/lizard-build/lizard-sdk/blob/main/CONTRIBUTING.md): local checks and test scope.

## License

[Apache-2.0](https://github.com/lizard-build/lizard-sdk/blob/main/LICENSE)
