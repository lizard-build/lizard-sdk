import asyncio
import json
import os
import time
from typing import AsyncIterator

# Node.js REPL script that reads JSON-encoded code from stdin and writes
# NDJSON output to stdout. One message per line, terminated by {"type":"done"}.
_NODE_REPL_SCRIPT = r"""
const vm = require('vm');
const readline = require('readline');

const ctx = vm.createContext({
  require,
  process,
  Buffer,
  setTimeout,
  setInterval,
  clearTimeout,
  clearInterval,
  console: {
    log:   (...a) => emit('stdout', a.map(String).join(' ') + '\n'),
    error: (...a) => emit('stderr', a.map(String).join(' ') + '\n'),
    warn:  (...a) => emit('stderr', a.map(String).join(' ') + '\n'),
    info:  (...a) => emit('stdout', a.map(String).join(' ') + '\n'),
  },
});

let count = 0;

function emit(type, data) {
  process.stdout.write(JSON.stringify({ type, data, ts: Date.now() }) + '\n');
}

const rl = readline.createInterface({ input: process.stdin, terminal: false });
rl.on('line', (line) => {
  const msg = JSON.parse(line);

  // Apply env vars
  if (msg.env_vars) {
    Object.assign(process.env, msg.env_vars);
  }

  let result = undefined;
  try {
    result = vm.runInContext(msg.code, ctx, { filename: '<sandbox>', displayErrors: false });
  } catch (e) {
    emit('error_obj', { name: e.name, message: e.message, traceback: e.stack || e.message });
    process.stdout.write(JSON.stringify({ type: 'done', execution_count: ++count }) + '\n');
    return;
  }

  if (result !== undefined) {
    let mime = 'text/plain';
    let data;
    try {
      data = JSON.stringify(result);
      mime = 'application/json';
    } catch (_) {
      data = String(result);
    }
    process.stdout.write(JSON.stringify({ type: 'result', mime, data }) + '\n');
  }

  process.stdout.write(JSON.stringify({ type: 'done', execution_count: ++count }) + '\n');
});
"""


class NodeExecutor:
    def __init__(self, cwd: str = "/home/user"):
        self.cwd = cwd
        self._proc: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()

    async def _ensure_proc(self):
        if self._proc and self._proc.returncode is None:
            return
        self._proc = await asyncio.create_subprocess_exec(
            "node",
            "-e",
            _NODE_REPL_SCRIPT,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.cwd,
        )

    async def execute(
        self, code: str, env_vars: dict | None = None
    ) -> AsyncIterator[dict]:
        async with self._lock:
            await self._ensure_proc()

            msg = json.dumps({"code": code, "env_vars": env_vars or {}})
            self._proc.stdin.write((msg + "\n").encode())
            await self._proc.stdin.drain()

            while True:
                raw = await self._proc.stdout.readline()
                if not raw:
                    yield {"type": "error", "name": "RuntimeError", "message": "Node process exited unexpectedly", "traceback": ""}
                    break

                try:
                    item = json.loads(raw.decode().strip())
                except json.JSONDecodeError:
                    continue

                if item.get("type") == "error_obj":
                    yield {"type": "error", **item["data"] if isinstance(item.get("data"), dict) else {"name": "Error", "message": str(item), "traceback": ""}}
                    continue

                yield item

                if item.get("type") == "done":
                    break

    async def close(self):
        if self._proc:
            try:
                self._proc.stdin.close()
                await self._proc.wait()
            except Exception:
                pass
