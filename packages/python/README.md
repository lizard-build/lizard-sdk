# Lizard SDK for Python

Run commands, work with files and execute code in Linux sandboxes (Firecracker microVMs). The SDK also manages Lizard apps, databases, storage and projects.

## Install

Requires Python 3.10+. The Python client is synchronous.

```sh
pip install lizard-sdk
```

Create an API key and project at [lizard.build](https://lizard.build), then set:

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

## Machine size

Sandboxes come in three sizes: `small` (2 vCPU / 4 GB, $0.0162/h), `medium` (4 vCPU / 8 GB, $0.0324/h, the default) and `large` (8 vCPU / 16 GB, $0.0648/h). Billing is flat by size, per second while the sandbox runs; measured CPU/RAM are not charged, egress is free, and volumes bill separately.

```python
sandbox = lizard.create("base", size="large")
```

## Stream command output

Inside the `with` block above:

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

The `desktop` template runs XFCE and Chromium you can watch in a browser and an agent can drive:

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

Treat `info.url` like a credential: anyone with it can see and control the desktop. Share `info.view_only_url` when someone only needs to watch. See the [desktop guide](../../docs/sandboxes.md#desktop-computer-use).

## Run Python

Run Python with the `interpreter` template. Each process command starts a separate Python process, so Python variables do not survive between calls; use `CodeSandbox` (below) when they should.

```python
from lizard import Sandbox

sandbox = Sandbox.create("interpreter", project_id="proj_123", timeout_ms=300_000)
try:
    result = sandbox.process.exec_("python -c 'print(2 ** 10)'")
    print(result.stdout, result.stderr, result.exit_code)
finally:
    sandbox.kill()
```

To run code snippets with state carried between calls, use `CodeSandbox` (`runCode` / `run_code`): it boots the `interpreter` template and runs Python in a persistent Jupyter kernel inside the sandbox. See [Run code](https://github.com/lizard-build/lizard-sdk/blob/main/docs/sandboxes.md#run-code-codesandbox).

## Run code with state (CodeSandbox)

`CodeSandbox` boots the `interpreter` template and runs Python in a persistent Jupyter kernel inside the sandbox: variables survive between calls, the value of the last expression and matplotlib charts come back in `results`, and exceptions in `error`.

```python
from lizard import CodeSandbox

with CodeSandbox.create(project_id="proj_123") as sandbox:
    sandbox.run_code("x = 21")
    run = sandbox.run_code("x * 2")
    print(run.results[0].data)  # "42"
```

`language="bash"` (and `"javascript"` where `node` is installed; the `interpreter` template does not ship it) runs each call as a fresh process with no shared state.

## Configuration

The SDK reads `LIZARD_API_KEY` and, optionally, `LIZARD_API_URL` (default: `https://lizard.build`). You can also pass `api_key` and `api_url` to the constructor or static sandbox methods.

Pass `timeout_ms` to `create()` to set the sandbox lifetime. The default is five minutes. `timeout_ms` on `process.exec_()` or `run_code()` controls that call, not the sandbox lifetime.

## Runtime limits

Each sandbox is a Firecracker microVM with its own kernel. Use volumes mounted at `/workspace` to keep files after a sandbox ends. `pause()`/`resume()` keep memory and running processes; `snapshot()` is ready in about 2 s and `Sandbox.restore()` starts a copy in about 0.4 s; `fork()` clones a running sandbox. File watching and sandbox log streaming are not available on Firecracker sandboxes yet, volumes cannot be resized yet, and a sandbox with a volume attached cannot be forked. See the [snapshot guide](../../docs/sandboxes.md#pause-resume-snapshots-and-fork).

`get_host()` returns a hostname without `https://`; the port is private, so send `sandbox.access_token` as the `X-Lizard-Access-Token` header (or use `expose_port()`, which also returns a browser `url` carrying the token). File writes accept text or bytes (binary is sent exactly); `read_bytes()` supports binary downloads.

## Current command and lifetime limits

Command results contain stdout, stderr, and the exit code. Command timeouts are limited to 1–600 seconds. The command options `envs`, `workdir` and `user` apply to that command; create-time `envs` apply to every command, and create-time `metadata` is returned by `getInfo()` / `get_info()`.

The SDK and CLI default to a five-minute lifetime. The raw API and dashboard default to no expiration. Set an explicit lifetime: `timeoutMs: 0` at creation disables expiration; a positive value sets a deadline. `setTimeout` accepts 1000–2147483647 ms, not zero. Commands do not reset the deadline. This is not an idle timer.

## Learn more

- [Sandbox reference](https://github.com/lizard-build/lizard-sdk/blob/main/docs/sandboxes.md)
- [Platform guide](https://github.com/lizard-build/lizard-sdk/blob/main/docs/platform.md)
- [CLI coverage and migration](https://github.com/lizard-build/lizard-sdk/blob/main/docs/cli-parity.md)
- [Source and issues](https://github.com/lizard-build/lizard-sdk)

[Apache-2.0](https://github.com/lizard-build/lizard-sdk/blob/main/LICENSE)
