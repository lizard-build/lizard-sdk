# Lizard SDK for TypeScript

Run commands, work with files and execute code in Linux sandboxes on Kubernetes. The SDK also manages Lizard apps, databases, storage and projects.

## Install

Requires Node.js 18+.

```sh
npm install @lizard-build/sdk
```

Create an API key and project at [lizard.build](https://lizard.build), then set:

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

## Machine size

Sandboxes come in three sizes: `small` (2 vCPU / 4 GB, $0.009/h), `medium` (4 vCPU / 8 GB, $0.018/h, the default) and `large` (8 vCPU / 16 GB, $0.036/h). Billing is flat by size, per second while the sandbox runs; measured CPU/RAM are not charged, egress is free, and volumes bill separately.

```ts
const sandbox = await lizard.create('base', { size: 'large' })
```

## Stream command output

Inside the `try` block above:

```ts
const result = await sandbox.process.exec('printf "hello\\n"', {
  timeoutMs: 30_000,
  onStdout: chunk => process.stdout.write(chunk),
  onStderr: chunk => process.stderr.write(chunk),
})
if (result.exitCode !== 0) throw new Error(result.stderr)
```

## Desktop (computer use)

The `desktop` template runs XFCE and Chromium you can watch in a browser and an agent can drive:

```ts
import { Sandbox } from '@lizard-build/sdk'

const sandbox = await Sandbox.create('desktop', { project: 'my-project' })
const { url, viewOnlyUrl } = await sandbox.desktop.start() // open `url` in a browser
await sandbox.desktop.openUrl('https://example.com')
await sandbox.desktop.click(640, 400)
await sandbox.desktop.type('hello')
await sandbox.desktop.press('Return')
const png: Uint8Array = await sandbox.desktop.screenshot()
```

Treat `url` like a credential: anyone with it can see and control the desktop. Share `viewOnlyUrl` when someone only needs to watch. See the [desktop guide](../../docs/sandboxes.md#desktop-computer-use).

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

`CodeSandbox`, `runCode` / `run_code`, and execution-context methods remain in the SDK, but the hosted template catalog does not provide their required execution server. The legacy default `code-interpreter-v1` is unavailable. Changing its name to `interpreter` does not enable this API. Use `Sandbox.create("interpreter")` and process commands as shown below.

## Configuration

The SDK reads `LIZARD_API_KEY` and, optionally, `LIZARD_API_URL` (default: `https://lizard.build`). You can also pass `apiKey` and `apiUrl` to the constructor or static sandbox methods.

Pass `timeoutMs` to `create()` to set the sandbox lifetime. The default is five minutes. `timeoutMs` on `process.exec()` or `runCode()` controls that call, not the sandbox lifetime.

## Runtime limits

Sandboxes run on Kubernetes. Use volumes mounted at `/workspace` to keep files after a sandbox ends. CRIU pause/resume and private snapshots preserve running memory and workspace files. Snapshot pools keep five copies warm by default and can be paused to release idle compute. Fork and file watching remain unsupported. See the [snapshot lifecycle guide](../../docs/sandboxes.md#snapshots-and-criu-pause-resume).

`getHost()` returns a hostname without `https://`. File writes accept UTF-8 text or valid UTF-8 bytes; `readBytes()` supports binary downloads.

## Current command and lifetime limits

Command results contain stdout, stderr, and the exit code. Command timeouts are limited to 1–600 seconds. The current runtime does not apply the SDK command options `envs`, `workdir`, or `user`; set the directory and environment in the shell command when needed. Create-time `envs` and `metadata` are also not applied.

The SDK and CLI default to a five-minute lifetime. The raw API and dashboard default to no expiration. Set an explicit lifetime: `timeoutMs: 0` at creation disables expiration; a positive value sets a deadline. `setTimeout` accepts 1000–2147483647 ms, not zero. Commands do not reset the deadline. This is not an idle timer.

## Learn more

- [Sandbox reference](https://github.com/lizard-build/lizard-sdk/blob/main/docs/sandboxes.md)
- [Platform guide](https://github.com/lizard-build/lizard-sdk/blob/main/docs/platform.md)
- [CLI coverage and migration](https://github.com/lizard-build/lizard-sdk/blob/main/docs/cli-parity.md)
- [Source and issues](https://github.com/lizard-build/lizard-sdk)

[Apache-2.0](https://github.com/lizard-build/lizard-sdk/blob/main/LICENSE)
