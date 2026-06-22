import sys
import io
import traceback
import base64
import json
import time
from contextlib import redirect_stdout, redirect_stderr
from typing import AsyncIterator


class PythonExecutor:
    def __init__(self, cwd: str = "/home/user"):
        self.globals: dict = {"__name__": "__main__", "__builtins__": __builtins__}
        self.cwd = cwd
        self.execution_count = 0

    async def execute(
        self, code: str, env_vars: dict | None = None
    ) -> AsyncIterator[dict]:
        import os

        saved_cwd = os.getcwd()
        saved_env: dict[str, str | None] = {}

        try:
            os.chdir(self.cwd)

            if env_vars:
                for k, v in env_vars.items():
                    saved_env[k] = os.environ.get(k)
                    os.environ[k] = v

            stdout_buf = io.StringIO()
            stderr_buf = io.StringIO()

            error_out = None
            result_out = None

            try:
                with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
                    import importlib
                    importlib.invalidate_caches()
                    compiled = compile(code, "<sandbox>", "exec")
                    exec(compiled, self.globals)

                    # Capture last expression value if code ends with an expression
                    lines = code.strip().splitlines()
                    if lines:
                        try:
                            last_expr = compile(lines[-1], "<sandbox>", "eval")
                            val = eval(last_expr, self.globals)
                            if val is not None:
                                result_out = _to_result(val)
                        except SyntaxError:
                            pass

            except Exception as e:
                error_out = {
                    "type": "error",
                    "name": type(e).__name__,
                    "message": str(e),
                    "traceback": traceback.format_exc(),
                }

            stdout_val = stdout_buf.getvalue()
            stderr_val = stderr_buf.getvalue()

            if stdout_val:
                yield {"type": "stdout", "data": stdout_val, "ts": _ts()}

            if stderr_val:
                yield {"type": "stderr", "data": stderr_val, "ts": _ts()}

            if result_out:
                yield result_out

            if error_out:
                yield error_out

        finally:
            os.chdir(saved_cwd)
            for k, v in saved_env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

        self.execution_count += 1
        yield {"type": "done", "execution_count": self.execution_count}


def _ts() -> int:
    return int(time.time() * 1000)


def _to_result(val) -> dict:
    # Matplotlib figure → PNG
    try:
        import matplotlib.pyplot as plt
        import matplotlib.figure

        if isinstance(val, matplotlib.figure.Figure):
            buf = io.BytesIO()
            val.savefig(buf, format="png", bbox_inches="tight")
            buf.seek(0)
            return {
                "type": "result",
                "mime": "image/png",
                "data": base64.b64encode(buf.read()).decode(),
            }
    except ImportError:
        pass

    # Anything with _repr_html_
    if hasattr(val, "_repr_html_"):
        html = val._repr_html_()
        if html:
            return {"type": "result", "mime": "text/html", "data": html}

    # JSON-serialisable value
    try:
        json.dumps(val)
        return {"type": "result", "mime": "application/json", "data": json.dumps(val)}
    except (TypeError, ValueError):
        pass

    return {"type": "result", "mime": "text/plain", "data": repr(val)}
