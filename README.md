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

## Pause and Resume

Sandboxes can be paused mid-execution and resumed exactly where they left off — including installed packages, in-memory state, and running processes. Pausing freezes the microVM's vCPUs; memory and processes stay in the host's RAM and are not written to disk, so a paused sandbox does not survive a host failure. This makes Lizard sandboxes well-suited for long-running AI agent workflows where you want to stop and continue across separate invocations.

Pausing does not stop the sandbox timeout — a paused sandbox is still deleted at its original expiry (default 5 minutes). Pass `timeoutMs: 0` (`timeout_ms=0` in Python) at create time to opt out of expiry.

```ts
// Boot and set up the environment once (reusing the `lizard` client from above)
const sandbox = await lizard.create('code-interpreter-v1')
await sandbox.process.exec('pip install numpy pandas scikit-learn')
const id = sandbox.sandboxId
await sandbox.pause()

// Later — resume instantly (no reinstall needed)
const resumed = await lizard.connect(id)
const result = await resumed.process.exec('python -c "import sklearn; print(sklearn.__version__)"')
console.log(result.stdout)
await resumed.kill()
```

```python
# reusing the `lizard` client from above
sandbox = lizard.create("code-interpreter-v1")
sandbox.process.exec_("pip install numpy pandas scikit-learn")
sandbox_id = sandbox.sandbox_id
sandbox.pause()

# Resume later — environment is exactly as left
resumed = lizard.connect(sandbox_id)
result = resumed.process.exec_("python -c 'import sklearn; print(sklearn.__version__)'")
print(result.stdout)
resumed.kill()
```

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

Connect to an existing sandbox by ID. If the sandbox is paused, it is automatically resumed.

### `Sandbox.list(opts?)`

List all running sandboxes for the authenticated account.

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

Freeze and unfreeze the microVM's vCPUs. Memory and running processes are kept in the host's RAM, not written to disk. The timeout keeps running while paused.

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
