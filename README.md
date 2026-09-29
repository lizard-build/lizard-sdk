# Lizard SDK

[![npm](https://img.shields.io/npm/v/@lizard-build/sdk)](https://www.npmjs.com/package/@lizard-build/sdk)
[![PyPI](https://img.shields.io/pypi/v/lizard-sdk)](https://pypi.org/project/lizard-sdk/)
[![Checks](https://github.com/lizard-build/lizard-sdk/actions/workflows/test.yml/badge.svg)](https://github.com/lizard-build/lizard-sdk/actions)

**Run code, work with files, and build AI agents in Linux sandboxes on Kubernetes.**

Lizard provides TypeScript and Python SDKs for sandboxes and the cloud services around them: apps, databases, storage, projects and API keys.

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

## Run code

Use `CodeSandbox` for Python, JavaScript and Bash execution with output callbacks and execution contexts. Variables and imports survive between calls in the same context while the sandbox runs.

```ts
import { CodeSandbox } from '@lizard-build/sdk'

const sandbox = await CodeSandbox.create({ project: 'my-project' })
try {
  const setup = await sandbox.runCode('total = 6 * 7', { timeoutMs: 60_000 })
  if (setup.error) throw setup.error
  const result = await sandbox.runCode('print(total)', { timeoutMs: 60_000 })
  if (result.error) throw result.error
  console.log(result.stdout) // 42
} finally {
  await sandbox.kill()
}
```

```python
from lizard import CodeSandbox

with CodeSandbox.create(project="my-project") as sandbox:
    setup = sandbox.run_code("total = 6 * 7")
    if setup.error:
        raise RuntimeError(setup.error.message)
    result = sandbox.run_code("print(total)")
    if result.error:
        raise RuntimeError(result.error.message)
    print(result.stdout)  # 42
```

Both SDKs use the `code-interpreter-v1` template by default. Template availability and installed tools depend on the platform and region.

## What you can do

| Task | TypeScript | Python |
| --- | --- | --- |
| Run a shell command | `sandbox.process.exec(cmd)` | `sandbox.process.exec_(cmd)` |
| Read or write a file | `sandbox.fs.read(path)` / `write(path, text)` | Same method names |
| Run code | `sandbox.runCode(code)` on `CodeSandbox` | `sandbox.run_code(code)` on `CodeSandbox` |
| Expose an HTTP port | `sandbox.getHost(port)` | `sandbox.get_host(port)` |
| Reconnect to a running sandbox | `Sandbox.connect(id)` | `Sandbox.connect(id)` |
| Keep files across sessions | `lizard.volumes.getOrCreate(name)` | `lizard.volumes.get_or_create(name)` |
| Resize a volume in place | `lizard.volumes.resize(name, sizeGb)` | `lizard.volumes.resize(name, size_gb)` |
| Manage cloud apps | `lizard.services`, `projects`, `addons` | Same namespaces |

See the [sandbox reference](https://github.com/lizard-build/lizard-sdk/blob/main/docs/sandboxes.md) for configuration, streaming, ports, volumes, errors and method names in both languages.

## Runtime and persistence

Sandboxes run on **Kubernetes**. Files outside an attached persistent volume last only for the sandbox's lifetime. Mount a volume at `/workspace` to keep files across sessions. A volume preserves files; it does not preserve running processes or memory.

The Kubernetes backend returns **HTTP 501** for pause, resume, fork, snapshot creation and snapshot restore. The SDK keeps these methods for API compatibility. Use `connect()` for a running sandbox and volumes for files that must outlive it.

## Documentation

- [TypeScript guide](https://github.com/lizard-build/lizard-sdk/blob/main/packages/js/README.md) and [Python guide](https://github.com/lizard-build/lizard-sdk/blob/main/packages/python/README.md): setup and runnable examples.
- [Sandbox reference](https://github.com/lizard-build/lizard-sdk/blob/main/docs/sandboxes.md): commands, files, code, ports, lifecycle and persistence.
- [Platform guide](https://github.com/lizard-build/lizard-sdk/blob/main/docs/platform.md): projects, workspaces, scoped keys and cloud services.
- [CLI coverage and migration](https://github.com/lizard-build/lizard-sdk/blob/main/docs/cli-parity.md): native APIs, optional CLI adapter and backend limits.
- [Contributing](https://github.com/lizard-build/lizard-sdk/blob/main/CONTRIBUTING.md): local checks and test scope.

## License

[Apache-2.0](https://github.com/lizard-build/lizard-sdk/blob/main/LICENSE)
