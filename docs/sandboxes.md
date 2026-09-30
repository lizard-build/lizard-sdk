# Sandbox reference

[TypeScript quickstart](../packages/js/README.md) · [Python quickstart](../packages/python/README.md) · [Platform guide](platform.md)

Sandboxes are Linux environments running on Kubernetes. `Sandbox` provides shell commands, files and ports. Each sandbox needs an API key and a project. The hosted runtime uses runc and shares the host kernel. The legacy `CodeSandbox` API is not supported by the current hosted templates.

## Configuration

| TypeScript option | Python option | Purpose |
| --- | --- | --- |
| `project` | `project` | Project ID, slug or unique name |
| `projectId` | `project_id` | Exact ID for static `Sandbox.create()`; takes precedence over `project` |
| `apiKey` | `api_key` | API key; defaults to `LIZARD_API_KEY` |
| `apiUrl` | `api_url` | API base URL; defaults to `LIZARD_API_URL` or `https://lizard.build` |
| `size` | `size` | `'small'` (2 vCPU / 4 GB, $0.009/h), `'medium'` (4 vCPU / 8 GB, $0.018/h) or `'large'` (8 vCPU / 16 GB, $0.036/h); default `'medium'`. Cannot be combined with a private snapshot |
| `snapshotId` | `snapshot_id` | Create from a private saved snapshot; see [Snapshots](#snapshots-and-criu-pause-resume) |
| `timeoutMs` | `timeout_ms` | Sandbox lifetime on `create()`; default 300,000 ms |
| `envs` | `envs` | Accepted by the SDK but not applied by the current create API |
| `metadata` | `metadata` | Accepted by the SDK but not applied by the current create API |
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

Both return stdout, stderr and an exit code. A nonzero command exit code is a result you must check; request failures throw or raise. Adding an output callback enables streaming while the method still waits for completion. Do not rely on `onPid` / `on_pid` being emitted by the current runtime.

Command results contain stdout, stderr, and the exit code. Command timeouts are limited to 1–600 seconds. The current runtime does not apply the SDK command options `envs`, `workdir`, or `user`; set the directory and environment in the shell command when needed. Create-time `envs` and `metadata` are also not applied.

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

Use absolute paths. Writes accept text or valid UTF-8 bytes; arbitrary binary uploads are unsupported. Binary downloads use `readBytes()` / `read_bytes()`. File watching returns HTTP 501 on the current runtime.

## Python execution

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

### Legacy code-interpreter API

`CodeSandbox`, `runCode` / `run_code`, and execution-context methods remain in the SDK, but the hosted template catalog does not provide their required execution server. The legacy default `code-interpreter-v1` is unavailable. Changing its name to `interpreter` does not enable this API. Use `Sandbox.create("interpreter")` and process commands as shown below.

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

Attached volumes mount at `/workspace`. Only files on that attached volume survive the sandbox; without a volume, `/workspace` is temporary. Each volume allows one sandbox attachment at a time. Other paths and in-memory state do not survive a stopped sandbox. A volume is node-local, so the platform places the sandbox in the volume's region. Omit `region` when attaching a volume.

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

### Resizing a volume

`volumes.resize(nameOrId, sizeGb)` grows or shrinks a volume **in place and online**, even while a sandbox has it mounted. The size is a quota, so no data is copied, the call finishes in well under a second, and the running sandbox sees the new size immediately. A shrink must leave at least 10% of the new size free, otherwise it fails with `code: 'volume_too_full_to_shrink'`. `getOrCreate` never changes an existing volume's size.

```ts
const info = await lizard.volumes.resize('agent-files', 20)   // VolumeInfo, sizeGb: 20
```

```python
info = lizard.volumes.resize("agent-files", 20)               # VolumeInfo, size_gb=20
```

In Python the classmethod is `Volume.resize(project_id, name_or_id, size_gb)` and the instance method is `volume.resize_to(project_id, size_gb)`, because a class cannot have both under one name (the same reason delete is `Volume.remove` / `volume.delete`).

Error codes: `volume_too_full_to_shrink`, `volume_resize_in_progress` and `volume_not_provisioned` (a just-created volume; retry in a few seconds) raise `ConflictError`; `volume_capacity_unavailable` (no room on the volume's node) raises `LizardError`; `volume_resize_timeout` raises `TimeoutError` and leaves the size unchanged; `invalid_volume_size` means outside the project's limits.

## Lifecycle

| Task | TypeScript | Python |
| --- | --- | --- |
| Reconnect by ID | `Sandbox.connect(id)` | `Sandbox.connect(id)` |
| Get status | `sandbox.getInfo()` | `sandbox.get_info()` |
| Change lifetime | `sandbox.setTimeout(ms)` | `sandbox.set_timeout(ms)` |
| List sandboxes in a project | `Sandbox.list({ projectId })` | `Sandbox.list(project_id=...)` |
| Kill a sandbox | `sandbox.kill()` | `sandbox.kill()` |

`connect()` checks sandbox metadata without changing its state. It does not recreate an expired sandbox. `Lizard.list()` lists sandboxes visible to the credential; it does not filter by the client's project. Use `Sandbox.list()` with the project ID for a project-specific list.

## Snapshots and CRIU pause/resume

Private snapshots capture a running app's memory and workspace files. Close active clients and terminals and stop workspace writes before capture. Attached persistent volumes cannot be captured. Snapshot creation is asynchronous; wait until ready before restoring. Warm copies default to five (configurable from one to ten); a depleted pool can return HTTP 503 until it refills. Fast warm claims do not guarantee a 100 ms API response.

```ts
const source = await Sandbox.create('base', { projectId, timeoutMs: 0 })
let snapshotId: string | undefined
let clone: Sandbox | undefined
try {
  // Start the application, then disconnect its clients before capture.
  const saved = await source.snapshot('my-app', { poolSize: 5 })
  snapshotId = saved.id
  await Sandbox.waitForSnapshot(saved.id)
  clone = await Sandbox.restore(saved.id)
  await Sandbox.pauseSnapshot(saved.id) // deletes idle warm copies, keeps clone running
  await Sandbox.resumeSnapshot(saved.id)
  await Sandbox.waitForSnapshot(saved.id)
  await clone.pause()
  await clone.waitForStatus('paused')
  await clone.resume()
  await clone.waitForStatus('running')
} finally {
  if (clone) await clone.kill()
  if (snapshotId) await Sandbox.deleteSnapshot(snapshotId)
  await source.kill()
}
```

```python
source = Sandbox.create("base", project_id=project_id, timeout_ms=0)
saved = None
clone = None
try:
    saved = source.snapshot("my-app", pool_size=5)
    Sandbox.wait_for_snapshot(saved["id"])
    clone = Sandbox.restore(saved["id"])
    Sandbox.pause_snapshot(saved["id"])
    Sandbox.resume_snapshot(saved["id"])
    Sandbox.wait_for_snapshot(saved["id"])
    clone.pause()
    clone.wait_for_status("paused")
    clone.resume()
    clone.wait_for_status("running")
finally:
    if clone:
        clone.kill()
    if saved:
        Sandbox.delete_snapshot(saved["id"])
    source.kill()
```

Use `Sandbox.getSnapshot(id)` / `Sandbox.get_snapshot(id)` to inspect status, `Sandbox.snapshots(projectId)` / `Sandbox.snapshots(project_id)` to list, and `Sandbox.setSnapshotWarmPool(id, count)` / `Sandbox.set_snapshot_warm_pool(id, count)` to resize the warm pool. Both `Sandbox.create({snapshotId, projectId})` and `Sandbox.create(snapshot_id=..., project_id=...)` also support private snapshots.

Snapshot pause preserves immutable saved images, disables replenishment and releases idle warm copies and image cache pins. Resume recreates the configured pool. Capture/build/verification resources are cleaned up automatically; saved images must remain for restore. Deleting a snapshot keeps already claimed sandboxes running. A paused snapshot stays paused after its workspace is unfrozen.

Sandbox `pause()` and `resume()` queue asynchronous operations and return a boolean. The wait helpers report capture errors and time out instead of polling forever. A sandbox resumes with the same ID and saved state. `fork()` still returns HTTP 501 on Kubernetes.

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
| `AuthenticationError` | HTTP 401 or 403: invalid key or insufficient access |
| `NotFoundError` | HTTP 404: resource missing or no longer available |
| `ConflictError` | HTTP 409: conflicting state, such as a volume name already in use |
| `TimeoutError` | HTTP 408 or 504 |
| `LizardError` | Other API failures, including unsupported operations |
| `ConfigApplyError` | Platform config saved, but a deploy or restart action failed; inspect `result` before retrying |

Some direct HTTP calls, including code-interpreter requests, expose native fetch/httpx errors. Local timeouts can also raise native transport errors. `kill()` returns `false` / `False` for an already missing sandbox. Check command exit codes and code execution errors separately from API failures.
