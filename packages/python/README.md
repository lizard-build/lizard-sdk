# Lizard SDK for Python

Run commands, work with files and execute code in Linux sandboxes on Kubernetes. The SDK also manages Lizard apps, databases, storage and projects.

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

Sandboxes come in three sizes: `small` (2 vCPU / 4 GB, $0.009/h), `medium` (4 vCPU / 8 GB, $0.018/h, the default) and `large` (8 vCPU / 16 GB, $0.036/h). Billing is flat by size, per second while the sandbox runs; measured CPU/RAM are not charged, egress is free, and volumes bill separately.

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

Run Python with the `interpreter` template. Each process command starts a separate Python process, so Python variables do not survive between calls. Save intermediate results to files. The API returns stdout, stderr, and an exit code; it does not return typed notebook results or chart objects.

```python
from lizard import Sandbox

sandbox = Sandbox.create("interpreter", project_id="proj_123", timeout_ms=300_000)
try:
    result = sandbox.process.exec_("python -c 'print(2 ** 10)'")
    print(result.stdout, result.stderr, result.exit_code)
finally:
    sandbox.kill()
```

`CodeSandbox`, `runCode` / `run_code`, and execution-context methods remain in the SDK, but the hosted template catalog does not provide their required execution server. The legacy default `code-interpreter-v1` is unavailable. Changing its name to `interpreter` does not enable this API. Use `Sandbox.create("interpreter")` and process commands as shown below.

## Configuration

The SDK reads `LIZARD_API_KEY` and, optionally, `LIZARD_API_URL` (default: `https://lizard.build`). You can also pass `api_key` and `api_url` to the constructor or static sandbox methods.

Pass `timeout_ms` to `create()` to set the sandbox lifetime. The default is five minutes. `timeout_ms` on `process.exec_()` or `run_code()` controls that call, not the sandbox lifetime.

## Runtime limits

Sandboxes run on Kubernetes. Use volumes mounted at `/workspace` to keep files after a sandbox ends. CRIU pause/resume and private snapshots preserve running memory and workspace files. Snapshot pools keep five copies warm by default and can be paused to release idle compute. Fork and file watching remain unsupported. See the [snapshot lifecycle guide](../../docs/sandboxes.md#snapshots-and-criu-pause-resume).

`get_host()` returns a hostname without `https://`. File writes accept UTF-8 text or valid UTF-8 bytes; `read_bytes()` supports binary downloads.

## Current command and lifetime limits

Command results contain stdout, stderr, and the exit code. Command timeouts are limited to 1–600 seconds. The current runtime does not apply the SDK command options `envs`, `workdir`, or `user`; set the directory and environment in the shell command when needed. Create-time `envs` and `metadata` are also not applied.

The SDK and CLI default to a five-minute lifetime. The raw API and dashboard default to no expiration. Set an explicit lifetime: `timeoutMs: 0` at creation disables expiration; a positive value sets a deadline. `setTimeout` accepts 1000–2147483647 ms, not zero. Commands do not reset the deadline. This is not an idle timer.

## Learn more

- [Sandbox reference](https://github.com/lizard-build/lizard-sdk/blob/main/docs/sandboxes.md)
- [Platform guide](https://github.com/lizard-build/lizard-sdk/blob/main/docs/platform.md)
- [CLI coverage and migration](https://github.com/lizard-build/lizard-sdk/blob/main/docs/cli-parity.md)
- [Source and issues](https://github.com/lizard-build/lizard-sdk)

[Apache-2.0](https://github.com/lizard-build/lizard-sdk/blob/main/LICENSE)
