# Sandbox reference

[TypeScript quickstart](../packages/js/README.md) · [Python quickstart](../packages/python/README.md) · [Platform guide](platform.md)

Sandboxes are Linux environments, each a Firecracker microVM with its own kernel; one boots in under a second. `Sandbox` provides shell commands, files, ports, pause/resume, snapshots and fork; `CodeSandbox` adds stateful code execution. Each sandbox needs an API key and a project.

## Configuration

| TypeScript option | Python option | Purpose |
| --- | --- | --- |
| `project` | `project` | Project ID, slug or unique name |
| `projectId` | `project_id` | Exact ID for static `Sandbox.create()`; takes precedence over `project` |
| `apiKey` | `api_key` | API key; defaults to `LIZARD_API_KEY` |
| `apiUrl` | `api_url` | API base URL; defaults to `LIZARD_API_URL` or `https://lizard.build` |
| `size` | `size` | `'small'` (2 vCPU / 4 GB, $0.009/h), `'medium'` (4 vCPU / 8 GB, $0.018/h) or `'large'` (8 vCPU / 16 GB, $0.036/h); default `'medium'`. Cannot be combined with a private snapshot |
| `snapshotId` | `snapshot_id` | Create from a private saved snapshot; see [Snapshots](#pause-resume-snapshots-and-fork) |
| `timeoutMs` | `timeout_ms` | Sandbox lifetime on `create()`; default 300,000 ms |
| `envs` | `envs` | Environment variables set in the sandbox, visible to every command |
| `metadata` | `metadata` | Your own string labels, returned by `getInfo()` / `get_info()` |
| `region` | `region` | Region ID; omit to use the platform default |
| `volumeName` / `volumeId` | `volume_name` / `volume_id` | Attach a persistent volume at `/workspace` |
| `lizardToken` | `lizard_token` | Inject a Lizard key for tools inside the sandbox |

`Lizard({ project })` / `Lizard(project=...)` resolves the project for sandbox creation and volumes. `project` is optional for platform APIs. Use an exact project ID when names are ambiguous. Configuration comes from the environment or explicit options; the SDK does not load `.env` files itself.

Pricing is flat by size: the hourly price above, billed per second while the sandbox runs. Measured CPU and RAM are not charged, and sandbox egress is free. Attached volumes bill separately. A sandbox created from a private snapshot runs on the machine the snapshot was captured on and is billed by measured usage; `size` is ignored there. There are no `cpus` / `memoryMb` options.

The default template is `base`. Choose a template from the current catalog. Enabled templates include `base`, `codex`, `interpreter` and `desktop` (see [Desktop](#desktop-computer-use)); availability depends on the region and pool capacity. `interpreter` includes Python and common data libraries. Check tool versions inside your sandbox. The public CLI does not provide a custom-template upload flow.

The SDK and CLI default to a five-minute lifetime. The raw API and dashboard default to no expiration. Set an explicit lifetime: `timeoutMs: 0` at creation disables expiration; a positive value sets a deadline. `setTimeout` accepts 1000–2147483647 ms, not zero. Commands do not reset the deadline. This is not an idle timer.

## Commands and output

These snippets assume a running `sandbox`. Use them inside the `try/finally` or `with` block from the quickstart.

```ts
const result = await sandbox.process.exec('printf "hello\\n"', {
  timeoutMs: 30_000,
  onStdout: chunk => process.stdout.write(chunk),
  onStderr: chunk => process.stderr.write(chunk),
})
if (result.exitCode !== 0) throw new Error(result.stderr)
```

```python
result = sandbox.process.exec_(
    'printf "hello\\n"',
    timeout_ms=30_000,
    on_stdout=lambda chunk: print(chunk, end=""),
    on_stderr=lambda chunk: print(chunk, end=""),
)
if result.exit_code != 0:
    raise RuntimeError(result.stderr)
```

Both return stdout, stderr and an exit code. A nonzero command exit code is a result you must check; request failures throw or raise. Adding an output callback enables streaming while the method still waits for completion. `onPid` / `on_pid` is called once with the process's pid before any output, so a running command can be signalled with `process.kill(pid)`.

Command results contain stdout, stderr, and the exit code. Command timeouts are limited to 1–600 seconds. The options `envs`, `workdir` and `user` (e.g. `user: 'user'`, the template's unprivileged account) apply to that command; create-time `envs` apply to every command.

| Process control | TypeScript | Python |
| --- | --- | --- |
| List commands started with `exec` | `process.list()` → `{ pid, cmd: string[], command, cwd, tag }` | `process.list()` → `ProcessInfo` |
| Signal a command and its children | `process.kill(pid, 'SIGKILL')` | `process.kill(pid, "SIGKILL")` |

`kill` signals the whole process tree, so a shell's children die with it.

## Files

| Operation | TypeScript | Python |
| --- | --- | --- |
| Write text or bytes | `fs.write(path, data)` | `fs.write(path, data)` |
| Read text | `fs.read(path)` | `fs.read(path)` |
| Read bytes | `fs.readBytes(path)` | `fs.read_bytes(path)` |
| List a directory | `fs.list(path)` | `fs.list(path)` |
| Inspect a path | `fs.stat(path)` | `fs.stat(path)` |
| Create a directory | `fs.makeDir(path)` | `fs.make_dir(path)` |
| Move a path | `fs.move(from, to)` | `fs.move(src, dst)` |
| Remove a path | `fs.remove(path)` | `fs.remove(path)` |

Use absolute paths. Writes accept text (stored as UTF-8) or bytes, which are sent base64-encoded and stored exactly; read binary files back with `readBytes()` / `read_bytes()`. Pass `user` to write or read as that Linux user (the file is then owned by it). A missing path raises `NotFoundError`. `list()` and `stat()` entries carry `type` (`'file'` / `'dir'`), `size`, `mode` (a number, e.g. `0o644`), `permissions` (`-rw-r--r--`), `owner`, `group` and `modTime` (unix ms). `move()` creates the destination's parent directories. File watching is not available on Firecracker sandboxes yet (HTTP 501).

## Python execution

Run Python with the `interpreter` template. Each process command starts a separate Python process, so Python variables do not survive between calls; use [`CodeSandbox`](#run-code-codesandbox) when they should.

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

## Run code (CodeSandbox)

`CodeSandbox` boots the `interpreter` template and runs code through the same exec API as `process.exec`; there is no extra server or port. Python runs in a **persistent Jupyter kernel** per context inside the sandbox, so variables, imports and functions survive between calls.

```ts
import { CodeSandbox } from '@lizard-build/sdk'

const sandbox = await CodeSandbox.create({ projectId })
try {
  await sandbox.runCode('import pandas as pd\ndf = pd.DataFrame({"x": [1, 2, 3]})')
  const run = await sandbox.runCode('df.x.sum()', { onStdout: s => process.stdout.write(s) })
  console.log(run.results[0].data)   // "6"
  const bad = await sandbox.runCode('1/0')
  console.log(bad.error?.name)       // "ZeroDivisionError"
} finally {
  await sandbox.kill()
}
```

```python
from lizard import CodeSandbox

with CodeSandbox.create(project_id=project_id) as sandbox:
    sandbox.run_code('import pandas as pd\ndf = pd.DataFrame({"x": [1, 2, 3]})')
    run = sandbox.run_code("df.x.sum()", on_stdout=lambda s: print(s, end=""))
    print(run.results[0].data)      # "6"
    print(sandbox.run_code("1/0").error.name)  # "ZeroDivisionError"
```

An `Execution` has `stdout`, `stderr`, `results` (rich output: the value of the last expression as `text/plain`, matplotlib charts and images as base64 `image/png`, HTML, ...), `error` (`name`, `message`, `traceback`) and `executionCount`. A code error is a result; request failures throw or raise.

- **Contexts.** `createContext({ language, cwd })` / `create_context(language, cwd)` starts a separate kernel with its own variables and working directory; pass it as `context`. `listContexts()`, `restartContext(ctx)` (clears its state) and `deleteContext(ctx)` manage them. Without a context, each language uses its own default one.
- **Timeouts.** `timeoutMs` / `timeout_ms` (default 60 s) bounds one call. A Python kernel that runs past it is interrupted, keeps its state, and the result's `error.name` is `TimeoutError`.
- **`envs`** apply to that one call.
- **Other languages.** `bash` and `javascript` run each call as a fresh process: no state carries over and `results` stays empty. `javascript` needs `node`, which the `interpreter` template does not ship. On a template without Jupyter (e.g. `base`), Python also runs as a fresh process per call.
- Kernels live in the microVM, so they survive `pause()`/`resume()` and are copied by `snapshot()` and `fork()`.

## HTTP ports

After starting an HTTP server that listens on `0.0.0.0` inside the sandbox, publish its port. The port is **private**: every request needs the sandbox's access token, as the `X-Lizard-Access-Token` header, or once as `?lizard_token=<token>` in a browser (which then gets a cookie).

```ts
const { hostname, url, accessToken } = await sandbox.exposePort(3000)
console.log(url) // open in a browser; it carries the token
const res = await fetch(`https://${hostname}/api`, { headers: { 'X-Lizard-Access-Token': accessToken } })
// When the route is no longer needed:
await sandbox.unexpose(3000)
```

```python
exposed = sandbox.expose_port(3000)
print(exposed.url)  # open in a browser; it carries the token
res = httpx.get(f"https://{exposed.hostname}/api", headers={"X-Lizard-Access-Token": exposed.access_token})
# When the route is no longer needed:
sandbox.unexpose(3000)
```

`getHost(port)` / `get_host(port)` does the same and returns only the **hostname without a scheme**; it also stores the token on the sandbox as `sandbox.accessToken` / `sandbox.access_token`. Keep the sandbox and server running while using the route.

## Persistent files

Attached volumes mount at `/workspace`. Only files on that attached volume survive the sandbox; without a volume, `/workspace` is temporary. Each volume allows one sandbox attachment at a time; `attachedTo` / `attached_to` on its info names that sandbox. A sandbox with a volume attached cannot be forked. Other paths and in-memory state do not survive a stopped sandbox. A volume is node-local, so the platform places the sandbox in the volume's region. Omit `region` when attaching a volume.

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

This example keeps the volume for future sessions. A volume's name is unique within a project; `getOrCreate` returns the existing volume when the name is taken, while `create` raises `ConflictError`. New volumes are 1–50 GB (default 5). Use `volumes.list()` and `volumes.get(nameOrId)` to find it later; `volumes.delete(nameOrId)` permanently removes it and its files. Static `Volume` methods take an explicit project ID.

### Resizing a volume

**Firecracker volumes (the default) cannot be resized yet**: `volumes.resize()` fails with `LizardError` (HTTP 400, `code: 'volume_not_resizable'`). Create a volume at the size you need, or copy the data to a new, larger volume.

On a container volume, `volumes.resize(nameOrId, sizeGb)` grows or shrinks it in place, even while a sandbox has it mounted; a shrink must leave at least 10% of the new size free, otherwise it fails with `code: 'volume_too_full_to_shrink'`. `getOrCreate` never changes an existing volume's size.

```ts
const info = await lizard.volumes.resize('agent-files', 20)   // VolumeInfo, sizeGb: 20
```

```python
info = lizard.volumes.resize("agent-files", 20)               # VolumeInfo, size_gb=20
```

In Python the classmethod is `Volume.resize(project_id, name_or_id, size_gb)` and the instance method is `volume.resize_to(project_id, size_gb)`, because a class cannot have both under one name (the same reason delete is `Volume.remove` / `volume.delete`).

Error codes: `volume_not_resizable` (a Firecracker volume) raises `LizardError`; `volume_too_full_to_shrink`, `volume_resize_in_progress` and `volume_not_provisioned` (a just-created volume; retry in a few seconds) raise `ConflictError`; `volume_capacity_unavailable` (no room on the volume's node) raises `LizardError`; `volume_resize_timeout` raises `TimeoutError` and leaves the size unchanged; `invalid_volume_size` means outside the project's limits.

## Lifecycle

| Task | TypeScript | Python |
| --- | --- | --- |
| Reconnect by ID | `Sandbox.connect(id)` | `Sandbox.connect(id)` |
| Get status | `sandbox.getInfo()` | `sandbox.get_info()` |
| Change lifetime | `sandbox.setTimeout(ms)` | `sandbox.set_timeout(ms)` |
| List sandboxes in a project | `Sandbox.list({ projectId })` | `Sandbox.list(project_id=...)` |
| Kill a sandbox | `sandbox.kill()` | `sandbox.kill()` |

`connect()` checks sandbox metadata without changing its state. It does not recreate an expired sandbox. `Lizard.list()` lists sandboxes visible to the credential; it does not filter by the client's project. Use `Sandbox.list()` with the project ID for a project-specific list.

## Pause, resume, snapshots and fork

A sandbox is a microVM, so all of these keep **memory and running processes**, not just files.

| Operation | TypeScript | Python | Notes |
| --- | --- | --- | --- |
| Pause / resume | `pause()`, `resume()`, `waitForStatus(s)` | `pause()`, `resume()`, `wait_for_status(s)` | Same ID; processes continue where they stopped |
| Snapshot | `snapshot(name)` | `snapshot(name)` | `ready` when the call returns (about 2 s); the source keeps running |
| Restore | `Sandbox.restore(snapshotId)` | `Sandbox.restore(snapshot_id)` | A new sandbox from the snapshot in about 0.4 s; restore as often as you like |
| Fork | `fork({ count })` | `fork(count=...)` | 1–10 live copies of a running sandbox; the source keeps running |

```ts
const source = await Sandbox.create('base', { projectId })
let snapshotId: string | undefined
const copies: Sandbox[] = []
try {
  await source.process.exec("nohup sh -c 'i=0; while true; do i=$((i+1)); echo $i > /tmp/n; sleep 1; done' >/dev/null 2>&1 &")
  await source.pause()
  await source.waitForStatus('paused')
  await source.resume()
  await source.waitForStatus('running')          // the counter keeps counting

  const saved = await source.snapshot('counter')  // status 'ready'
  snapshotId = saved.id
  copies.push(await Sandbox.restore(saved.id))

  for (const f of await source.fork({ count: 2 })) {
    if (f.sandbox) copies.push(f.sandbox)
    else console.warn('fork failed:', f.error)
  }
} finally {
  for (const c of copies) await c.kill()
  if (snapshotId) await Sandbox.deleteSnapshot(snapshotId)
  await source.kill()
}
```

```python
source = Sandbox.create("base", project_id=project_id)
saved = None
copies = []
try:
    source.process.exec_("nohup sh -c 'i=0; while true; do i=$((i+1)); echo $i > /tmp/n; sleep 1; done' >/dev/null 2>&1 &")
    source.pause()
    source.wait_for_status("paused")
    source.resume()
    source.wait_for_status("running")          # the counter keeps counting

    saved = source.snapshot("counter")          # status "ready"
    copies.append(Sandbox.restore(saved["id"]))

    for f in source.fork(count=2):
        if f.sandbox:
            copies.append(f.sandbox)
        else:
            print("fork failed:", f.error)
finally:
    for c in copies:
        c.kill()
    if saved:
        Sandbox.delete_snapshot(saved["id"])
    source.kill()
```

`fork()` returns one entry per requested copy, in order: `{ sandbox, info }` (Python: a `ForkResult` with `sandbox` and `info`) or `{ error }` for a copy that could not be made, e.g. because of the account's sandbox limit. Each copy is billed like its source. A sandbox with a volume attached cannot be forked (`ConflictError`).

Use `Sandbox.getSnapshot(id)` / `Sandbox.get_snapshot(id)` to inspect a snapshot, `Sandbox.snapshots(projectId)` to list them, and `Sandbox.deleteSnapshot(id)` / `Sandbox.delete_snapshot(id)` to remove one; deleting a snapshot keeps sandboxes already restored from it running. `Sandbox.create({ snapshotId, projectId })` / `Sandbox.create(snapshot_id=..., project_id=...)` is the same as `restore`. `waitForSnapshot` / `wait_for_snapshot` returns immediately for a Firecracker snapshot.

Container sandboxes (the older runtime, `runtime: 'container'` in `getInfo()`) build snapshots asynchronously into a pool of warm copies instead: there `poolSize` (default five), `setSnapshotWarmPool`, `pauseSnapshot` / `resumeSnapshot` and `waitForSnapshot` matter, and `fork()` is not supported. These options are ignored for Firecracker snapshots.

## Desktop (computer use)

The `desktop` template runs a graphical desktop — Xvfb, XFCE and Chromium on `DISPLAY=:1` — that you can watch in a browser and an agent can drive with screenshots, mouse and keyboard. The desktop is not running when the sandbox boots; `desktop.start()` starts it (about a second) and publishes its noVNC stream. `DISPLAY` is set in the image, so anything you `exec` (for example a Playwright script or `xdotool`) talks to the same screen.

```ts
import { writeFileSync } from 'node:fs'

const sandbox = await Sandbox.create('desktop', { project: 'my-project' })
try {
  const { url, viewOnlyUrl } = await sandbox.desktop.start({ width: 1280, height: 800 })
  console.log('Watch and control:', url) // a credential — see below

  await sandbox.desktop.openUrl('https://example.com')
  await sandbox.desktop.click(640, 400)
  await sandbox.desktop.type('hello world')
  await sandbox.desktop.press('Return')
  writeFileSync('screen.png', await sandbox.desktop.screenshot())
} finally {
  await sandbox.kill()
}
```

```python
from pathlib import Path

with Sandbox.create("desktop", project="my-project") as sandbox:
    info = sandbox.desktop.start(width=1280, height=800)
    print("Watch and control:", info.url)  # a credential -- see below

    sandbox.desktop.open_url("https://example.com")
    sandbox.desktop.click(640, 400)
    sandbox.desktop.type("hello world")
    sandbox.desktop.press("Return")
    Path("screen.png").write_bytes(sandbox.desktop.screenshot())
```

| TypeScript | Python | What it does |
| --- | --- | --- |
| `start({ width?, height? })` | `start(width=, height=)` | Start the desktop (idempotent) and return `{ running, width, height, url, viewOnlyUrl }`. Size is 640–3840 × 480–2160, default 1280×800; a running desktop keeps its size |
| `info()` | `info()` | Same shape, without starting anything |
| `stop()` | `stop()` | Stop the desktop and unpublish the stream |
| `screenshot()` | `screenshot()` | PNG of the whole screen, as `Uint8Array` / `bytes`; the desktop must be running |
| `click(x, y, { button?, double? })` | `click(x, y, button=, double=)` | `button` is `'left'` (default), `'right'` or `'middle'` |
| `moveMouse(x, y)` | `move_mouse(x, y)` | Move the pointer |
| `drag(fromX, fromY, toX, toY)` | `drag(from_x, from_y, to_x, to_y)` | Left-button drag |
| `type(text)` | `type(text)` | Type text into the focused window |
| `press(keys)` | `press(keys)` | xdotool key names or chords: `'Return'`, `'ctrl+l'`, `['ctrl+a', 'Delete']` |
| `scroll(direction, amount = 3)` | `scroll(direction, amount=3)` | `'up'`, `'down'`, `'left'` or `'right'`, in wheel clicks |
| `cursorPosition()` | `cursor_position()` | `{ x, y }` / `(x, y)` |
| `openUrl(url)` | `open_url(url)` | Open a URL in a new Chromium window; returns once Chromium is launched, not when the page has loaded |

Input and screenshots run inside the sandbox with `xdotool` and `scrot` through the normal exec path. Every argument is sent as an argv array and never passes through a shell, so text a model or user asks you to type cannot run commands. `process.exec` / `process.exec_` accept an argv array too, for your own commands.

**Treat both URLs like credentials.** The stream is published on a public hostname, and each URL carries its access token and a VNC password. Anyone with `url` can see and control the desktop, including everything signed in inside it. `viewOnlyUrl` can only watch — the VNC server enforces this, not the page — so share that one when someone only needs to look. Do not log either URL. Stopping and restarting the desktop keeps the same URLs; killing the sandbox revokes them.

On any other template the desktop calls fail with HTTP 400 and `code === 'DESKTOP_NOT_SUPPORTED'`. `screenshot()` has the desktop write a PNG to a temporary file in `/tmp`, downloads it with the binary file read, then deletes it, so full-size screenshots are not limited by exec output.

## Errors

Most platform and sandbox methods map HTTP failures to these exported errors. Each carries the HTTP `status` (`status_code` in Python) and, when the API sends one, a machine-readable `code`:

| Error | Meaning |
| --- | --- |
| `PaymentRequiredError` | HTTP 402: the account has to start Pro, start it now, or pay an invoice before it can create anything; see below |
| `AuthenticationError` | HTTP 401 or 403: invalid key or insufficient access |
| `NotFoundError` | HTTP 404: resource missing or no longer available |
| `ConflictError` | HTTP 409: conflicting state, such as a volume name already in use |
| `TimeoutError` | HTTP 408 or 504 |
| `LizardError` | Other API failures, including unsupported operations |
| `ConfigApplyError` | Platform config saved, but a deploy or restart action failed; inspect `result` before retrying |

When the API sends `{error: "SOME_CODE", message: "..."}`, the sentence becomes the error message and `SOME_CODE` the `code`.

`PaymentRequiredError` has the platform's sentence as its message; show it to the user as is. `code` is `PAYMENT_REQUIRED` (`INSUFFICIENT_CREDITS` from older servers, `UNPAID_INVOICE` when an old invoice blocks a new Pro subscription). `paymentStatus` / `payment_status` says why: `trial_available`, `subscription_required`, `trial_credits_used`, `past_due`, `paused`, or a status of the old prepaid credits (`grace`, `frozen`, `card_required`, `credits_required`). The links are `subscribeUrl`, `billingUrl`, `topupUrl` and `invoiceUrl` (snake_case in Python), and `url` picks the one to open: Start Pro for the first two statuses, the invoice, the Credits page for prepaid credits, otherwise Billing. The user finishes payment in the browser; retry the call after they do.

```ts
try {
  await Sandbox.create('base', { projectId })
} catch (err) {
  if (err instanceof PaymentRequiredError) console.log(`${err.message}\n${err.url}`)
  else throw err
}
```

```python
try:
    Sandbox.create("base", project_id=project_id)
except PaymentRequiredError as err:
    print(err.message, err.url, sep="\n")
```

Some direct HTTP calls expose native fetch/httpx errors. Local timeouts can also raise native transport errors. `kill()` returns `false` / `False` for an already missing sandbox. Check command exit codes and code execution errors separately from API failures.
