# Lizard TypeScript SDK

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

## Run code

`CodeSandbox` uses the `code-interpreter-v1` template by default. Code errors appear in `result.error`; request failures throw.

```ts
import { CodeSandbox } from '@lizard-build/sdk'

const sandbox = await CodeSandbox.create({ project: 'my-project' })
try {
  const result = await sandbox.runCode('print(6 * 7)', {
    language: 'python',
    timeoutMs: 60_000,
    onStdout: chunk => process.stdout.write(chunk),
  })
  if (result.error) throw result.error
} finally {
  await sandbox.kill()
}
```

## Configuration

The SDK reads `LIZARD_API_KEY` and, optionally, `LIZARD_API_URL` (default: `https://lizard.build`). You can also pass `apiKey` and `apiUrl` to the constructor or static sandbox methods.

Pass `timeoutMs` to `create()` to set the sandbox lifetime. The default is five minutes. `timeoutMs` on `process.exec()` or `runCode()` controls that call, not the sandbox lifetime.

## Runtime limits

Sandboxes run on Kubernetes. Use volumes mounted at `/workspace` to keep files after a sandbox ends. Pause, resume, fork, snapshot creation and snapshot restore return HTTP 501 on the current backend.

`getHost()` returns a hostname without `https://`. File writes accept UTF-8 text or valid UTF-8 bytes; `readBytes()` supports binary downloads.

## Learn more

- [Sandbox reference](https://github.com/lizard-build/lizard-sdk/blob/main/docs/sandboxes.md)
- [Platform guide](https://github.com/lizard-build/lizard-sdk/blob/main/docs/platform.md)
- [CLI coverage and migration](https://github.com/lizard-build/lizard-sdk/blob/main/docs/cli-parity.md)
- [Source and issues](https://github.com/lizard-build/lizard-sdk)

[Apache-2.0](https://github.com/lizard-build/lizard-sdk/blob/main/LICENSE)
