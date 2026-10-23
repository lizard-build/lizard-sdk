# Lizard SDK for Python

Lizard (lizard.build) provides cloud sandboxes for AI agents and code execution. Lizard SDK is the official Python client for creating and controlling Lizard Sandboxes.

Run AI-generated Python in a stateful code interpreter, execute shell commands, read and write files, or control a browser and desktop. Each sandbox runs as a Firecracker microVM with its own kernel.

## Use cases

- Execute AI-generated code with a [stateful Python code interpreter](https://lizard.build/docs/sandboxes/code-interpreter/).
- Run coding agents such as [Claude Code](https://lizard.build/docs/sandboxes/guides/claude-code/) in a cloud sandbox.
- Automate a browser or desktop with [screenshots, clicks and keyboard input](https://github.com/lizard-build/lizard-sdk/blob/main/docs/sandboxes.md#desktop-computer-use).
- Open an agent's dev server through a [private preview URL](https://lizard.build/docs/sandboxes/preview-urls/).

## Install

Requires Python 3.10+. The Python client is synchronous.

```sh
pip install lizard-sdk
```

Start with Lizard Pro or its trial; see [billing and trial terms](https://lizard.build/docs/platform/billing/). Create an API key and project at [lizard.build](https://lizard.build), then set:

```sh
export LIZARD_API_KEY="your-api-key"
```

## Create a sandbox

Save this as `quickstart.py`. Replace `my-project` with your project's ID, slug or unique name, then run `python quickstart.py`.

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

The context manager kills the sandbox when the block ends, including when it raises an error. If you create a sandbox without `with`, call `sandbox.kill()` in a `finally` block.

## Run code with state (CodeSandbox)

`CodeSandbox` boots the `interpreter` template and runs Python in a persistent Jupyter kernel inside the sandbox: variables survive between calls, the value of the last expression and matplotlib charts come back in `results`, and exceptions in `error`.

```python
from lizard import CodeSandbox

with CodeSandbox.create(project="my-project", timeout_ms=300_000) as sandbox:
    setup = sandbox.run_code("x = 21")
    if setup.error:
        raise RuntimeError(f"{setup.error.name}: {setup.error.message}")
    run = sandbox.run_code("x * 2")
    if run.error:
        raise RuntimeError(f"{run.error.name}: {run.error.message}")
    print(run.results[0].data)  # "42"
```

`language="bash"` and `language="javascript"` (the `interpreter` template ships Node 22) run each call as a fresh process with no shared state. See the [code interpreter guide](https://lizard.build/docs/sandboxes/code-interpreter/).

## Account, pricing and machine size

Lizard Pro costs $19 a month, taxes included, with $19 of usage each month. Unused usage does not carry over. Usage above that amount is pay as you go at the published rates. New accounts can start a 7-day trial with $5 of usage; a card is required, and nothing is charged until the trial ends. If trial usage runs out, workloads pause until Pro starts. See the current [billing and trial terms](https://lizard.build/docs/platform/billing/).

Sandbox rates below were checked on October 23, 2026. See [current sizes and prices](https://lizard.build/docs/platform/limits/#sandbox-sizes) before estimating costs.

Sandboxes come in three sizes: `small` (2 vCPU / 4 GB, $0.0162/h), `medium` (4 vCPU / 8 GB, $0.0324/h, the default) and `large` (8 vCPU / 16 GB, $0.0648/h). Billing is flat by size, per second while the sandbox runs, including idle time. CPU and RAM are included. The sandbox egress allowance is [2 TB per account over a rolling 30 days](https://lizard.build/docs/platform/limits/#sandbox-egress), with no separate per-GB charge. A successful pause stops compute charges; storage in Persistent Volumes is billed separately, including while paused.

```python
with lizard.create("base", size="large") as sandbox:
    result = sandbox.process.exec_("python -c 'print(2 ** 10)'")
    if result.exit_code != 0:
        raise RuntimeError(result.stderr)
    print(result.stdout)
```

## Stream command output

Inside the `with` block in the first sandbox example:

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

## Desktop (computer use)

The `desktop` template runs an Openbox desktop with Chromium, streamed to a browser over WebRTC (with noVNC as the fallback). You can watch it, and an agent can drive it:

```python
from lizard import Sandbox

with Sandbox.create("desktop", project="my-project") as sandbox:
    info = sandbox.desktop.start()  # open info.url in a browser
    sandbox.desktop.open_url("https://example.com")
    sandbox.desktop.click(640, 400)
    sandbox.desktop.type("hello")
    sandbox.desktop.press("Return")
    png: bytes = sandbox.desktop.screenshot()
```

Treat `info.url` like a credential: anyone with it can see and control the desktop. Share `info.view_only_url` when someone only needs to watch. See the [desktop guide](https://github.com/lizard-build/lizard-sdk/blob/main/docs/sandboxes.md#desktop-computer-use).

## Run Python

Run Python with the `interpreter` template. Each process command starts a separate Python process, so Python variables do not survive between calls; use `CodeSandbox` when they should.

```python
from lizard import Sandbox

sandbox = Sandbox.create("interpreter", project="my-project", timeout_ms=300_000)
try:
    result = sandbox.process.exec_("python -c 'print(2 ** 10)'")
    if result.exit_code != 0:
        raise RuntimeError(result.stderr)
    print(result.stdout, result.stderr, result.exit_code)
finally:
    sandbox.kill()
```

To keep state between calls, use `CodeSandbox.run_code()`. See the [code execution reference](https://github.com/lizard-build/lizard-sdk/blob/main/docs/sandboxes.md#run-code-codesandbox).

## Configuration

The SDK reads `LIZARD_API_KEY` and, optionally, `LIZARD_API_URL` (default: `https://lizard.build`). You can also pass `api_key` and `api_url` to the constructor or static sandbox methods.

Lizard Git (`lizard.git`: repositories, pull requests, CI and the rest) reads `LIZARD_GIT_URL` (default `https://lizard.build/git`) and needs a key with no scopes. See the [Lizard Git guide](https://github.com/lizard-build/lizard-sdk/blob/main/docs/platform.md#lizard-git).

Pass `timeout_ms` to `create()` to set the sandbox lifetime. The default is five minutes. `timeout_ms` on `process.exec_()` or `run_code()` controls that call, not the sandbox lifetime.

## Runtime limits

Lizard Sandboxes run as Firecracker microVMs, each with its own kernel. Use Persistent Volumes mounted at `/workspace` to keep files after a sandbox ends. `pause()`/`resume()` keep memory and running processes; `snapshot()` is ready in about 2 s and `Sandbox.restore()` starts a copy in about 0.4 s; `fork()` clones a running sandbox. File watching and sandbox log streaming are not available yet. Volumes can grow but not shrink, and a sandbox with a volume attached cannot be forked. See the [snapshot guide](https://github.com/lizard-build/lizard-sdk/blob/main/docs/sandboxes.md#pause-resume-snapshots-and-fork).

`get_host()` returns a hostname without `https://`; the port is private, so send `sandbox.access_token` as the `X-Lizard-Access-Token` header (or use `expose_port()`, which also returns a browser `url` carrying the token). File writes accept text or bytes (binary is sent exactly); `read_bytes()` supports binary downloads.

## Current command and lifetime limits

Command results contain stdout, stderr, and the exit code. Command timeouts are limited to 1–600 seconds. The command options `envs`, `workdir` and `user` apply to that command; create-time `envs` apply to every command, and create-time `metadata` is returned by `get_info()`.

The SDK and CLI default to a five-minute lifetime. The raw API and dashboard default to no expiration. Set an explicit lifetime: `timeout_ms=0` at creation disables expiration; a positive value sets a deadline. `set_timeout()` accepts 1000–2147483647 ms, not zero. Commands do not reset the deadline. This is not an idle timer.

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
