# Lizard SDK for TypeScript and JavaScript

Lizard (lizard.build) provides cloud sandboxes for AI agents and code execution. Lizard SDK is the official TypeScript and JavaScript client for creating and controlling Lizard Sandboxes.

Run AI-generated Python in a stateful code interpreter, execute shell commands, read and write files, or control a browser and desktop. Each sandbox runs as a Firecracker microVM with its own kernel.

## Use cases

- Execute AI-generated code with a [stateful Python code interpreter](https://lizard.build/docs/sandboxes/code-interpreter/).
- Run coding agents such as [Claude Code](https://lizard.build/docs/sandboxes/guides/claude-code/) in a cloud sandbox.
- Automate a browser or desktop with [screenshots, clicks and keyboard input](https://github.com/lizard-build/lizard-sdk/blob/main/docs/sandboxes.md#desktop-computer-use).
- Open an agent's dev server through a [private preview URL](https://lizard.build/docs/sandboxes/preview-urls/).

## Install

Requires Node.js 18+.

```sh
npm install @lizard-build/sdk
```

Start with Lizard Pro or its trial; see [billing and trial terms](https://lizard.build/docs/platform/billing/). Create an API key and project at [lizard.build](https://lizard.build), then set:

```sh
export LIZARD_API_KEY="your-api-key"
```

## Create a sandbox

Save this as `quickstart.mjs`. Replace `my-project` with your project's ID, slug or unique name, then run `node quickstart.mjs`.

```js
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

The package includes TypeScript declarations and ESM and CommonJS builds. For CommonJS, use `const { Lizard } = require('@lizard-build/sdk')` inside a program with an async entry point.

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

`language: 'bash'` and `language: 'javascript'` (the `interpreter` template ships Node 22) run each call as a fresh process with no shared state. See the [code interpreter guide](https://lizard.build/docs/sandboxes/code-interpreter/).

## Account, pricing and machine size

Lizard Pro costs $19 a month, taxes included, with $19 of usage each month. Unused usage does not carry over. Usage above that amount is pay as you go at the published rates. New accounts can start a 7-day trial with $5 of usage; a card is required, and nothing is charged until the trial ends. If trial usage runs out, workloads pause until Pro starts. See the current [billing and trial terms](https://lizard.build/docs/platform/billing/).

Sandbox rates below were checked on October 23, 2026. See [current sizes and prices](https://lizard.build/docs/platform/limits/#sandbox-sizes) before estimating costs.

Sandboxes come in three sizes: `small` (2 vCPU / 4 GB, $0.0162/h), `medium` (4 vCPU / 8 GB, $0.0324/h, the default) and `large` (8 vCPU / 16 GB, $0.0648/h). Billing is flat by size, per second while the sandbox runs, including idle time. CPU and RAM are included. The sandbox egress allowance is [2 TB per account over a rolling 30 days](https://lizard.build/docs/platform/limits/#sandbox-egress), with no separate per-GB charge. A successful pause stops compute charges; storage in Persistent Volumes is billed separately, including while paused.

```ts
const sandbox = await lizard.create('base', { size: 'large' })
try {
  const result = await sandbox.process.exec("python -c 'print(2 ** 10)'")
  if (result.exitCode !== 0) throw new Error(result.stderr)
  console.log(result.stdout)
} finally {
  await sandbox.kill()
}
```

## Stream command output

Inside the `try` block in the first sandbox example:

```ts
const result = await sandbox.process.exec('printf "hello\\n"', {
  timeoutMs: 30_000,
  onStdout: chunk => process.stdout.write(chunk),
  onStderr: chunk => process.stderr.write(chunk),
})
if (result.exitCode !== 0) throw new Error(result.stderr)
```

## Desktop (computer use)

The `desktop` template runs an Openbox desktop with Chromium, streamed to a browser over WebRTC (with noVNC as the fallback). You can watch it, and an agent can drive it:

```ts
import { Sandbox } from '@lizard-build/sdk'

const sandbox = await Sandbox.create('desktop', { project: 'my-project' })
try {
  const { url, viewOnlyUrl } = await sandbox.desktop.start() // open `url` in a browser
  await sandbox.desktop.openUrl('https://example.com')
  await sandbox.desktop.click(640, 400)
  await sandbox.desktop.type('hello')
  await sandbox.desktop.press('Return')
  const png: Uint8Array = await sandbox.desktop.screenshot()
} finally {
  await sandbox.kill()
}
```

Treat `url` like a credential: anyone with it can see and control the desktop. Share `viewOnlyUrl` when someone only needs to watch. See the [desktop guide](https://github.com/lizard-build/lizard-sdk/blob/main/docs/sandboxes.md#desktop-computer-use).

## Run Python

Run Python with the `interpreter` template. Each process command starts a separate Python process, so Python variables do not survive between calls; use `CodeSandbox` when they should.

```ts
import { Sandbox } from '@lizard-build/sdk'

const sandbox = await Sandbox.create('interpreter', {
  project: 'my-project', timeoutMs: 300_000,
})
try {
  const result = await sandbox.process.exec("python -c 'print(2 ** 10)'")
  if (result.exitCode !== 0) throw new Error(result.stderr)
  console.log(result.stdout, result.stderr, result.exitCode)
} finally {
  await sandbox.kill()
}
```

To keep state between calls, use `CodeSandbox.runCode()`. See the [code execution reference](https://github.com/lizard-build/lizard-sdk/blob/main/docs/sandboxes.md#run-code-codesandbox).

## Configuration

The SDK reads `LIZARD_API_KEY` and, optionally, `LIZARD_API_URL` (default: `https://lizard.build`). You can also pass `apiKey` and `apiUrl` to the constructor or static sandbox methods.

Lizard Git (`lizard.git`: repositories, pull requests, CI and the rest) reads `LIZARD_GIT_URL` (default `https://lizard.build/git`) and needs a key with no scopes. See the [Lizard Git guide](https://github.com/lizard-build/lizard-sdk/blob/main/docs/platform.md#lizard-git).

Pass `timeoutMs` to `create()` to set the sandbox lifetime. The default is five minutes. `timeoutMs` on `process.exec()` or `runCode()` controls that call, not the sandbox lifetime.

## Runtime limits

Lizard Sandboxes run as Firecracker microVMs, each with its own kernel. Use Persistent Volumes mounted at `/workspace` to keep files after a sandbox ends. `pause()`/`resume()` keep memory and running processes; `snapshot()` is ready in about 2 s and `Sandbox.restore()` starts a copy in about 0.4 s; `fork()` clones a running sandbox. File watching and sandbox log streaming are not available yet. Volumes can grow but not shrink, and a sandbox with a volume attached cannot be forked. See the [snapshot guide](https://github.com/lizard-build/lizard-sdk/blob/main/docs/sandboxes.md#pause-resume-snapshots-and-fork).

`getHost()` returns a hostname without `https://`; the port is private, so send `sandbox.accessToken` as the `X-Lizard-Access-Token` header (or use `exposePort()`, which also returns a browser `url` carrying the token). File writes accept text or bytes (binary is sent exactly); `readBytes()` supports binary downloads.

## Current command and lifetime limits

Command results contain stdout, stderr, and the exit code. Command timeouts are limited to 1–600 seconds. The command options `envs`, `workdir` and `user` apply to that command; create-time `envs` apply to every command, and create-time `metadata` is returned by `getInfo()`.

The SDK and CLI default to a five-minute lifetime. The raw API and dashboard default to no expiration. Set an explicit lifetime: `timeoutMs: 0` at creation disables expiration; a positive value sets a deadline. `setTimeout()` accepts 1000–2147483647 ms, not zero. Commands do not reset the deadline. This is not an idle timer.

## Other SDK capabilities

The SDK also manages apps, Managed Postgres, Managed Redis, Managed Object Storage and projects. See the [platform guide](https://github.com/lizard-build/lizard-sdk/blob/main/docs/platform.md).

## Learn more

- [Sandboxes overview and current limits](https://lizard.build/docs/sandboxes/)
- [Sandboxes quickstart](https://lizard.build/docs/sandboxes/quickstart/)
- [Billing and trial terms](https://lizard.build/docs/platform/billing/)
- [Sandbox reference](https://github.com/lizard-build/lizard-sdk/blob/main/docs/sandboxes.md)
- [Platform guide](https://github.com/lizard-build/lizard-sdk/blob/main/docs/platform.md)
- [CLI coverage and migration](https://github.com/lizard-build/lizard-sdk/blob/main/docs/cli-parity.md)
- [Source and issues](https://github.com/lizard-build/lizard-sdk)

[Apache-2.0](https://github.com/lizard-build/lizard-sdk/blob/main/LICENSE)
