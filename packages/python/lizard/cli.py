from __future__ import annotations
from dataclasses import dataclass
import json
import os
import subprocess


@dataclass
class CLIResult:
    code: int
    stdout: str
    stderr: str
    events: list


class LizardCLI:
    """Optional local CLI adapter. Requires lizard on PATH; never uses a shell.

    Does not add --yes or retry payments. The CLI's exit code is returned to the
    caller. Use the native APIs for streaming or large output.
    """

    def __init__(self, *, executable: str = "lizard", cwd: str | None = None,
                 api_key: str | None = None, api_url: str | None = None, timeout_ms: int = 600_000):
        self.executable, self.cwd = executable, cwd
        self.api_key, self.api_url, self.timeout_ms = api_key, api_url, timeout_ms

    def run(self, args: list[str], *, stdin: str | None = None) -> CLIResult:
        env = os.environ.copy()
        if self.api_key:
            env["LIZARD_API_KEY"] = env["LIZARD_TOKEN"] = self.api_key
        if self.api_url:
            env["LIZARD_API_URL"] = self.api_url
        result = subprocess.run([self.executable, "--json", *args], input=stdin,
                                capture_output=True, text=True, encoding="utf-8", cwd=self.cwd, env=env,
                                timeout=self.timeout_ms / 1000, shell=False)
        try:
            events = [json.loads(result.stdout)]
        except ValueError:
            events = []
            for line in result.stdout.splitlines():
                try:
                    events.append(json.loads(line))
                except ValueError:
                    continue
        return CLIResult(result.returncode, result.stdout, result.stderr, events)
