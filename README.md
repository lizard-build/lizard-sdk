# Lizard SDK

Firecracker microVM sandboxes for AI agents — boot a full Linux environment in milliseconds, run code, write files, and expose ports, all from your agent or CI pipeline.

Each sandbox is an isolated microVM with its own filesystem, network, and process namespace. Sandboxes can be paused — vCPUs frozen, memory and running processes kept — and resumed instantly, so a long-running agent session picks up without re-running setup.

## Install

```bash
# JavaScript / TypeScript
npm install @lizard-build/sdk

# Python
pip install lizard-sdk
```

## Quickstart

### JavaScript / TypeScript

```ts
import { Lizard } from '@lizard-build/sdk'

// A client is pinned to one project — sandboxes are billed per project, so a
// project is required. It can be the project's ID, slug, or name.
// apiKey defaults to the LIZARD_API_KEY env var.
const lizard = new Lizard({ project: 'my-project' })

// Boot a microVM from the 'base' template (Debian + Node.js 26)
const sandbox = await lizard.create('base')

// Write a file directly into the microVM filesystem
await sandbox.fs.write('/app/server.js', `
  const http = require('http')
  http.createServer((_, res) => res.end('hello from Lizard')).listen(3000)
`)

// Execute a process inside the microVM
await sandbox.process.exec('node /app/server.js &')

// Get a public HTTPS URL for port 3000 inside the sandbox
const url = sandbox.getHost(3000)
console.log(`Live at https://${url}`)

// Tear down the microVM when done
await sandbox.kill()
```

### Python

```python
from lizard import Lizard

# A client is pinned to one project — sandboxes are billed per project, so a
# project is required (its ID, slug, or name). api_key defaults to LIZARD_API_KEY.
lizard = Lizard(project="my-project")

# Boot a Python microVM from the 'code-interpreter-v1' template
sandbox = lizard.create("code-interpreter-v1")

# Write a script into the microVM filesystem
sandbox.fs.write("/app/main.py", """
import http.server, socketserver

class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"hello from Lizard")

with socketserver.TCPServer(("", 3000), Handler) as httpd:
    httpd.serve_forever()
""")

# Execute a process inside the microVM
sandbox.process.exec_("python /app/main.py &")

print(f"Live at https://{sandbox.get_host(3000)}")

sandbox.kill()
```

## Persisting Work Across Sandboxes

Sandboxes are **ephemeral**: killing one, or letting it hit its timeout, discards everything written inside it. State that has to outlive a sandbox goes on a **volume** — a separate disk mounted at `/data` that a later sandbox re-attaches.

A volume is node-local, so it fixes the region too. You don't thread a region through both calls: the sandbox is placed wherever its volume already lives.

```ts
const vol = await lizard.volumes.getOrCreate('agent-scratch', { sizeGb: 10 })

const first = await lizard.create('codex', { volumeName: 'agent-scratch' })
await first.process.exec('pip install numpy pandas && echo "notes" > /data/notes.txt')
await first.kill()          // sandbox gone, /data survives

const second = await lizard.create('codex', { volumeName: 'agent-scratch' })
console.log(await second.fs.read('/data/notes.txt'))   // "notes"
```

```python
vol = lizard.volumes.get_or_create("agent-scratch", size_gb=10)

first = lizard.create("codex", volume_name="agent-scratch")
first.process.exec_('echo "notes" > /data/notes.txt')
first.kill()                # sandbox gone, /data survives

second = lizard.create("codex", volume_name="agent-scratch")
print(second.fs.read("/data/notes.txt"))   # "notes"
```

Note that only `/data` survives — installed packages and in-memory state do not. Bake tooling into a template instead of reinstalling it per sandbox.

> `pause()` / `resume()` exist on the client but are **not implemented** for the current runtime and always fail with HTTP 501. Use a volume.

## Giving Each of Your Users Their Own Workspace

If you are building on top of Lizard and your users each need isolated resources, give each one a workspace and an API key scoped to it. They get isolation from each other; you keep one bill.

```ts
const lizard = new Lizard({ apiKey: process.env.LIZARD_API_KEY })

const ws  = await lizard.workspaces.create({ name: `user-${userId}` })
const prj = await lizard.projects.create({ workspaceId: ws.id, name: 'default' })
const key = await lizard.apiKeys.create({ name: `user-${userId}`, workspaces: [ws.id] })

// key.key is returned exactly once. Store it now.
await db.users.update(userId, { lizardKey: key.key })
```

That key reaches nothing outside `ws`, and it cannot mint a broader one — the server rejects that with an exact subset check. So it is safe to hand to the user, and safe to put **inside a sandbox** so agent code can use the CLI as that user:

```ts
const sandbox = await Sandbox.create('codex', {
  projectId: prj.id,
  lizardToken: key.key,        // scoped — bounded if it leaks
})
await sandbox.process.exec('lizard volume list')   // sees only this workspace
```

```python
ws = lizard.workspaces.create(name=f"user-{user_id}")
prj = lizard.projects.create(workspace_id=ws.id, name="default")
key = lizard.api_keys.create(name=f"user-{user_id}", workspaces=[ws.id])

sandbox = Sandbox.create("codex", project_id=prj.id, lizard_token=key.key)
sandbox.process.exec_("lizard volume list")
```

A key with **no** scope has full access to everything the creating account can reach — pass `workspaces` or `projects` unless you mean that.

## API

### `new Lizard({ project, apiKey?, apiUrl?, timeoutMs? })`

Create a client pinned to a project. Every sandbox is billed per project, so `project` is required — pass its ID, slug, or name (resolved to an ID on first use and cached). `apiKey` defaults to the `LIZARD_API_KEY` env var.

```ts
const lizard = new Lizard({ project: 'my-project' })
const sandbox = await lizard.create('base')
const sandbox = await lizard.create('code-interpreter-v1', { timeoutMs: 10 * 60 * 1000 })
```

### `Sandbox.create(template?, opts?)`

Boot a new Lizard microVM. Built-in templates: `base` (Debian + Node.js 26) and `code-interpreter-v1` (Python 3.14 + Node.js 26). Custom templates can be pushed via `lizard push`. A project is required — pass `project` (ID, slug, or name) or an exact `projectId` in `opts`, or use a `Lizard` client, which pins one for you.

```ts
const sandbox = await Sandbox.create('base', { project: 'my-project' })
const sandbox = await Sandbox.create('code-interpreter-v1', { project: 'my-project', timeoutMs: 10 * 60 * 1000 })
```

### `Sandbox.connect(sandboxId, opts?)`

Connect to an existing sandbox by ID. Throws `NotFoundError` if it has been killed or has expired.

### `Sandbox.list(opts?)`

List all running sandboxes for the authenticated account.

---

### Account and provisioning

| Namespace | Methods |
|---|---|
| `lizard.workspaces` | `list()`, `create({ name })`, `delete(id, { force? })`, `find(nameOrSlugOrId)` |
| `lizard.apiKeys` | `list()`, `create({ name, workspaces?, projects? })`, `delete(id)` |
| `lizard.projects` | `list({ workspaceId? })`, `get(id)`, `create({ workspaceId, name })`, `update(id, { name })`, `delete(id)` |
| `lizard.regions` | `list()` |
| `lizard.billing` | `balance()`, `transactions({ limit?, cursor?, includeUsage? })`, `summary()`, `live()` |
| `lizard.whoami()` | The account behind the credential — works for scoped keys too |
| `lizard.platform` | The raw HTTP client, for endpoints not wrapped yet |

`workspaces.delete()` is empty-only by default; the server refuses while any project, sandbox or volume remains. `{ force: true }` deletes the workspace and everything in it, irreversibly.

In Python the namespaces are `lizard.workspaces`, `lizard.api_keys`, `lizard.regions`, `lizard.billing`, and arguments are snake_case (`workspace_id`, `include_usage`).

### Volumes

| Method | Description |
|---|---|
| `lizard.volumes.getOrCreate(name, { sizeGb?, region? })` | The volume with this name, created if absent |
| `lizard.volumes.create(name, { sizeGb?, region? })` | Create; throws `ConflictError` if the name is taken |
| `lizard.volumes.get(nameOrId)` | Look one up |
| `lizard.volumes.list()` | Every volume in the client's project |
| `lizard.volumes.delete(nameOrId)` | Delete |

A volume's **name** is its key inside a project, so an agent can reconstruct it between runs without storing an id. The static `Volume.*` forms take an explicit `projectId` as their first argument.

`region` places the volume (see `lizard.regions.list()` for valid ids) and, because a volume is node-local, also fixes the region of any sandbox that mounts it. You normally set it here or nowhere.

---

### `sandbox.fs`

Read and write files inside the microVM filesystem.

| Method | Description |
|---|---|
| `fs.write(path, data)` | Write a file (string or bytes) |
| `fs.read(path)` | Read a file as a string |
| `fs.list(path)` | List directory contents |
| `fs.remove(path)` | Delete a file or directory |
| `fs.makeDir(path)` | Create a directory and parents |

### `sandbox.process`

Execute commands inside the microVM.

| Method | Description |
|---|---|
| `process.exec(cmd, opts?)` | Run a command and wait for it to finish |

`exec` returns `{ stdout, stderr, exitCode }` (JS) or `ProcessResult` (Python). In Python the method is named `exec_` because `exec` is a reserved keyword.

### `sandbox.getHost(port)`

Returns a public HTTPS URL for a port listening inside the microVM — no tunneling required.

```ts
await sandbox.process.exec('npx -y serve -p 3000 &')
const url = sandbox.getHost(3000)
// https://{sandboxId}-3000.sandbox.{region}.onlizard.com
```

### `sandbox.pause()` / `sandbox.resume()`

**Not implemented** for the current runtime — both always fail with HTTP 501. Use a [volume](#persisting-work-across-sandboxes) to carry work across sandboxes.

### `sandbox.kill()`

Terminate the sandbox and release all resources.

### `sandbox.setTimeout(ms)`

Extend or reduce the sandbox timeout.

---

## Environment Variables

| Variable | Description |
|---|---|
| `LIZARD_API_KEY` | API key (required — get one at [lizard.build](https://lizard.build)) |
| `LIZARD_API_URL` | Override the API base URL (default: `https://lizard.build`) |

The `X-API-Key` header is used for all authenticated requests.

## Deploy What You Build

Once your agent has produced a working app inside a sandbox, deploy it as a persistent Lizard service — no Dockerfile needed:

```bash
lizard up
```

Your sandbox template becomes the base, your code ships as a layer on top, and Lizard manages the Firecracker microVM fleet from there.

## License

Apache-2.0
