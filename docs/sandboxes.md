# Sandbox reference

[TypeScript quickstart](../packages/js/README.md) · [Python quickstart](../packages/python/README.md) · [Platform guide](platform.md)

Sandboxes are Linux environments running on Kubernetes. `Sandbox` provides shell commands, files and ports. `CodeSandbox` adds stateful code execution. Both need an API key and a project when you create a sandbox.

## Configuration

| TypeScript option | Python option | Purpose |
| --- | --- | --- |
| `project` | `project` | Project ID, slug or unique name |
| `projectId` | `project_id` | Exact ID for static `Sandbox.create()`; takes precedence over `project` |
| `apiKey` | `api_key` | API key; defaults to `LIZARD_API_KEY` |
| `apiUrl` | `api_url` | API base URL; defaults to `LIZARD_API_URL` or `https://lizard.build` |
| `timeoutMs` | `timeout_ms` | Sandbox lifetime on `create()`; default 300,000 ms |
| `envs` | `envs` | Environment variables inside the sandbox |
| `metadata` | `metadata` | String key/value labels |
| `region` | `region` | Region ID; omit to use the platform default |
| `volumeName` / `volumeId` | `volume_name` / `volume_id` | Attach a persistent volume at `/workspace` |
| `lizardToken` | `lizard_token` | Inject a Lizard key for tools inside the sandbox |

`Lizard({ project })` / `Lizard(project=...)` resolves the project for sandbox creation and volumes. `project` is optional for platform APIs. Use an exact project ID when names are ambiguous. Configuration comes from the environment or explicit options; the SDK does not load `.env` files itself.

The default template is `base` for `Sandbox` and `code-interpreter-v1` for `CodeSandbox`. Installed tools and template availability depend on the platform and region. Use a template that contains the runtime your command needs.

Set sandbox lifetime options on `create()`. Timeouts on command or code calls do not extend that lifetime. `setTimeout()` / `set_timeout()` changes the sandbox lifetime; `0` requests no automatic expiry, subject to platform policy. Explicitly kill sandboxes when finished.

## Commands and output

These snippets assume a running `sandbox`. Use them inside the `try/finally` or `with` block from the quickstart.

```ts
const result = await sandbox.process.exec('printf "hello\\n"', {
  workdir: '/tmp',
  envs: { APP_ENV: 'test' },
  timeoutMs: 30_000,
  onStdout: chunk => process.stdout.write(chunk),
  onStderr: chunk => process.stderr.write(chunk),
})
if (result.exitCode !== 0) throw new Error(result.stderr)
```

```python
result = sandbox.process.exec_(
    'printf "hello\\n"',
    workdir="/tmp",
    envs={"APP_ENV": "test"},
    timeout_ms=30_000,
    on_stdout=lambda chunk: print(chunk, end=""),
    on_stderr=lambda chunk: print(chunk, end=""),
)
if result.exit_code != 0:
    raise RuntimeError(result.stderr)
```

Both return stdout, stderr and an exit code. A nonzero command exit code is a result you must check; request failures throw or raise. Adding an output callback enables streaming while the method still waits for completion. `onPid` / `on_pid` supplies the process ID, which you can pass to `process.kill()`.

## Files

| Operation | TypeScript | Python |
| --- | --- | --- |
| Write UTF-8 text | `fs.write(path, text)` | `fs.write(path, text)` |
| Read text | `fs.read(path)` | `fs.read(path)` |
| Read bytes | `fs.readBytes(path)` | `fs.read_bytes(path)` |
| List a directory | `fs.list(path)` | `fs.list(path)` |
| Inspect a path | `fs.stat(path)` | `fs.stat(path)` |
| Create a directory | `fs.makeDir(path)` | `fs.make_dir(path)` |
| Move a path | `fs.move(from, to)` | `fs.move(src, dst)` |
| Remove a path | `fs.remove(path)` | `fs.remove(path)` |

Use absolute paths. Writes accept text or valid UTF-8 bytes; arbitrary binary uploads are unsupported. Binary downloads use `readBytes()` / `read_bytes()`. File watchers use polling through `getEvents()` / `get_events()`; call `close()` when done.

## Stateful code execution

Create a `CodeSandbox` to run Python, JavaScript or Bash. The default language is Python. Variables and imports survive between calls in the same execution context while the sandbox runs.

```ts
import { CodeSandbox } from '@lizard-build/sdk'

const sandbox = await CodeSandbox.create({ project: 'my-project' })
try {
  const context = await sandbox.createContext({ language: 'python' })
  try {
    const setup = await sandbox.runCode('value = 42', { context, timeoutMs: 60_000 })
    if (setup.error) throw setup.error
    const result = await sandbox.runCode('print(value)', { context, timeoutMs: 60_000 })
    if (result.error) throw result.error
    console.log(result.stdout)
  } finally {
    await sandbox.deleteContext(context)
  }
} finally {
  await sandbox.kill()
}
```

```python
from lizard import CodeSandbox

with CodeSandbox.create(project="my-project") as sandbox:
    context = sandbox.create_context(language="python")
    try:
        setup = sandbox.run_code("value = 42", context=context)
        if setup.error:
            raise RuntimeError(setup.error.message)
        result = sandbox.run_code("print(value)", context=context)
        if result.error:
            raise RuntimeError(result.error.message)
        print(result.stdout)
    finally:
        sandbox.delete_context(context)
```

Pass `language` or `context`, not both. A context separates interpreter state within one sandbox; use separate sandboxes for separate workloads. `result.results` contains rich output items, and `result.error` contains an error from the executed code. Transport failures throw or raise separately.

Use `onStdout` / `on_stdout`, `onStderr` / `on_stderr`, `onResult` / `on_result` and `onError` / `on_error` to receive output as it arrives. Set `timeoutMs` in TypeScript when you need a client deadline; it has no timer by default. Python's `timeout_ms` defaults to 60,000 ms.

## HTTP ports

After starting an HTTP server that listens on `0.0.0.0` inside the sandbox, register its port:

```ts
const hostname = await sandbox.getHost(3000)
console.log(`https://${hostname}`)
// When the route is no longer needed:
await sandbox.unexpose(3000)
```

```python
hostname = sandbox.get_host(3000)
print(f"https://{hostname}")
# When the route is no longer needed:
sandbox.unexpose(3000)
```

These methods return a **hostname without a scheme**, not a full URL. Keep the sandbox and server running while using the route. The route is public; add authentication in your application if it needs access control.

## Persistent files

Volumes mount at `/workspace`. Files there survive the sandbox that wrote them; other paths and in-memory state do not. A volume is node-local, so the platform places the sandbox in the volume's region. Omit `region` when attaching a volume.

```ts
import { Lizard } from '@lizard-build/sdk'

const lizard = new Lizard({ project: 'my-project' })
await lizard.volumes.getOrCreate('agent-files', { sizeGb: 10 })

const first = await lizard.create('base', { volumeName: 'agent-files' })
try {
  await first.fs.write('/workspace/notes.txt', 'Saved for the next session')
} finally {
  await first.kill()
}

const second = await lizard.create('base', { volumeName: 'agent-files' })
try {
  console.log(await second.fs.read('/workspace/notes.txt'))
} finally {
  await second.kill()
}
```

```python
from lizard import Lizard

lizard = Lizard(project="my-project")
lizard.volumes.get_or_create("agent-files", size_gb=10)

with lizard.create("base", volume_name="agent-files") as first:
    first.fs.write("/workspace/notes.txt", "Saved for the next session")

with lizard.create("base", volume_name="agent-files") as second:
    print(second.fs.read("/workspace/notes.txt"))
```

This example keeps the volume for future sessions. A volume's name is unique within a project. Use `volumes.list()` and `volumes.get(nameOrId)` to find it later; `volumes.delete(nameOrId)` permanently removes it and its files. Static `Volume` methods take an explicit project ID.

## Lifecycle

| Task | TypeScript | Python |
| --- | --- | --- |
| Reconnect by ID | `Sandbox.connect(id)` | `Sandbox.connect(id)` |
| Get status | `sandbox.getInfo()` | `sandbox.get_info()` |
| Change lifetime | `sandbox.setTimeout(ms)` | `sandbox.set_timeout(ms)` |
| List sandboxes in a project | `Sandbox.list({ projectId })` | `Sandbox.list(project_id=...)` |
| Kill a sandbox | `sandbox.kill()` | `sandbox.kill()` |

`connect()` checks sandbox metadata without changing its state. It does not recreate an expired sandbox. `Lizard.list()` lists sandboxes visible to the credential; it does not filter by the client's project. Use `Sandbox.list()` with the project ID for a project-specific list.

The Kubernetes backend returns HTTP 501 for `pause()`, `resume()`, `fork()`, `snapshot()` and `Sandbox.restore()`. These methods remain in the SDK for API compatibility. Snapshot listing and deletion do not imply support for snapshot creation. Reconnect to running sandboxes and use volumes to keep files across sessions.

## Errors

Most platform and sandbox methods map HTTP failures to these exported errors:

| Error | Meaning |
| --- | --- |
| `AuthenticationError` | HTTP 401 or 403: invalid key or insufficient access |
| `NotFoundError` | HTTP 404: resource missing or no longer available |
| `ConflictError` | HTTP 409: conflicting state, such as a volume name already in use |
| `TimeoutError` | HTTP 408 or 504 |
| `LizardError` | Other API failures, including unsupported operations |
| `ConfigApplyError` | Platform config saved, but a deploy or restart action failed; inspect `result` before retrying |

Some direct HTTP calls, including code-interpreter requests, expose native fetch/httpx errors. Local timeouts can also raise native transport errors. `kill()` returns `false` / `False` for an already missing sandbox. Check command exit codes and code execution errors separately from API failures.
