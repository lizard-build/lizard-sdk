# Lizard SDK

Firecracker microVM sandboxes for AI agents — boot a full Linux environment in milliseconds, run code, write files, and expose ports, all from your agent or CI pipeline.

Each sandbox is an isolated microVM with its own filesystem, network, and process namespace. Sandboxes can be snapshotted and resumed instantly, so long-running agent sessions survive restarts without re-running setup.

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
import { Sandbox } from '@lizard-build/sdk'

// Boot a Node.js microVM from the 'node22' template
const sandbox = await Sandbox.create('node22')

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
from lizard import Sandbox

# Boot a Python microVM from the 'python312' template
sandbox = Sandbox.create("python312")

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

Sandboxes can be snapshotted mid-execution and resumed exactly where they left off — including installed packages, in-memory state, and running processes. This makes Lizard sandboxes well-suited for long-running AI agent workflows where you want to checkpoint and continue across separate invocations.

```ts
// Boot and set up the environment once
const sandbox = await Sandbox.create('python312')
await sandbox.process.exec('pip install numpy pandas scikit-learn')
const id = sandbox.sandboxId
await sandbox.pause()

// Later — resume instantly from the snapshot (no reinstall needed)
const resumed = await Sandbox.connect(id)
const result = await resumed.process.exec('python -c "import sklearn; print(sklearn.__version__)"')
console.log(result.stdout)
await resumed.kill()
```

```python
from lizard import Sandbox

sandbox = Sandbox.create("python312")
sandbox.process.exec_("pip install numpy pandas scikit-learn")
sandbox_id = sandbox.sandbox_id
sandbox.pause()

# Resume later — environment is exactly as left
resumed = Sandbox.connect(sandbox_id)
result = resumed.process.exec_("python -c 'import sklearn; print(sklearn.__version__)'")
print(result.stdout)
resumed.kill()
```

## API

### `Sandbox.create(template?, opts?)`

Boot a new Lizard microVM. Built-in templates: `base`, `node22`, `python312`. Custom templates can be pushed via `lizard push`.

```ts
const sandbox = await Sandbox.create('node22')
const sandbox = await Sandbox.create('python312', { timeoutMs: 10 * 60 * 1000 })
```

### `Sandbox.connect(sandboxId, opts?)`

Connect to an existing sandbox by ID. If the sandbox is paused, it is automatically resumed from its last snapshot.

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

Snapshot and restore the microVM state. Useful for checkpointing long agent sessions.

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
