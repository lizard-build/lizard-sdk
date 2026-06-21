import asyncio
import json
import os
import time
from typing import AsyncIterator


class BashExecutor:
    def __init__(self, cwd: str = "/home/user"):
        self.cwd = cwd
        self.execution_count = 0

    async def execute(
        self, code: str, env_vars: dict | None = None
    ) -> AsyncIterator[dict]:
        env = {**os.environ, **(env_vars or {})}

        proc = await asyncio.create_subprocess_exec(
            "bash",
            "-c",
            code,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.cwd,
            env=env,
        )

        # Stream stdout and stderr concurrently
        async def read_stream(stream, output_type: str):
            while True:
                chunk = await stream.read(4096)
                if not chunk:
                    break
                yield {"type": output_type, "data": chunk.decode(errors="replace"), "ts": _ts()}

        stdout_items = []
        stderr_items = []

        async def collect(stream, items, output_type):
            async for item in read_stream(stream, output_type):
                items.append(item)

        await asyncio.gather(
            collect(proc.stdout, stdout_items, "stdout"),
            collect(proc.stderr, stderr_items, "stderr"),
        )

        await proc.wait()

        for item in stdout_items:
            yield item
        for item in stderr_items:
            yield item

        if proc.returncode != 0:
            yield {
                "type": "error",
                "name": "ExitError",
                "message": f"Process exited with code {proc.returncode}",
                "traceback": "",
            }

        self.execution_count += 1
        yield {"type": "done", "execution_count": self.execution_count}


def _ts() -> int:
    return int(time.time() * 1000)
