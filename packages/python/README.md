# Lizard Python SDK

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

## Run code

`CodeSandbox` uses the `code-interpreter-v1` template by default. Code errors appear in `result.error`; request failures raise an exception.

```python
from lizard import CodeSandbox

with CodeSandbox.create(project="my-project") as sandbox:
    result = sandbox.run_code(
        "print(6 * 7)",
        language="python",
        timeout_ms=60_000,
        on_stdout=lambda chunk: print(chunk, end=""),
    )
    if result.error:
        raise RuntimeError(result.error.message)
```

## Configuration

The SDK reads `LIZARD_API_KEY` and, optionally, `LIZARD_API_URL` (default: `https://lizard.build`). You can also pass `api_key` and `api_url` to the constructor or static sandbox methods.

Pass `timeout_ms` to `create()` to set the sandbox lifetime. The default is five minutes. `timeout_ms` on `process.exec_()` or `run_code()` controls that call, not the sandbox lifetime.

## Runtime limits

Sandboxes run on Kubernetes. Use volumes mounted at `/workspace` to keep files after a sandbox ends. Pause, resume, fork, snapshot creation and snapshot restore return HTTP 501 on the current backend.

`get_host()` returns a hostname without `https://`. File writes accept UTF-8 text or valid UTF-8 bytes; `read_bytes()` supports binary downloads.

## Learn more

- [Sandbox reference](https://github.com/lizard-build/lizard-sdk/blob/main/docs/sandboxes.md)
- [Platform guide](https://github.com/lizard-build/lizard-sdk/blob/main/docs/platform.md)
- [CLI coverage and migration](https://github.com/lizard-build/lizard-sdk/blob/main/docs/cli-parity.md)
- [Source and issues](https://github.com/lizard-build/lizard-sdk)

[Apache-2.0](https://github.com/lizard-build/lizard-sdk/blob/main/LICENSE)
