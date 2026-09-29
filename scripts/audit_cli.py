#!/usr/bin/env python3
"""Discover every CLI command and verify help execution. No resource mutations.

This is a discovery audit, not a live functional test. HTTP functionality is
covered separately by SDK contract tests and an approved live run.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess


def command_names(root, prefix=()):
    for command in root.get("subcommands", []):
        path = (*prefix, command["name"])
        yield " ".join(path)
        yield from command_names(command, path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cli", default="lizard")
    parser.add_argument("--output", type=Path, default=Path("cli-audit.json"))
    args = parser.parse_args()
    mapping = json.loads((Path(__file__).parents[1] / "tests/contracts/cli-coverage.json").read_text())
    root = subprocess.run([args.cli, "--help", "--json"], capture_output=True, text=True, timeout=30, check=True)
    schema = json.loads(root.stdout)
    found = set(command_names(schema["command"]))
    # Published 4.0.8 still exposes the five commands removed in CLI PR #13.
    # Only audit legacy commands when the inspected binary actually exposes them.
    commands = mapping["commands"] + [row for row in mapping.get("legacyCommands", []) if row["command"] in found]
    known = {row["command"] for row in commands}

    def check(row):
        result = subprocess.run([args.cli, *row["command"].split(), "--help", "--json"], capture_output=True, text=True, timeout=30)
        try:
            payload = json.loads(result.stdout)
            valid = isinstance(payload.get("command"), dict)
        except ValueError:
            valid = False
        return {**row, "helpExitCode": result.returncode, "helpJsonValid": valid,
                "functionalLiveTest": "not run"}

    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(check, commands))
    report = {"cliVersion": schema["version"], "expectedVersion": mapping["cliVersion"],
              "missingMappings": sorted(found - known), "removedCommands": sorted(known - found),
              "commands": rows, "note": "Help discovery only. Native SDK contracts run in the test suites; live effects require a separate approved run."}
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    failures = [r for r in rows if r["helpExitCode"] or not r["helpJsonValid"]]
    print(f"{len(rows)} commands: {len(rows) - len(failures)} help checks passed; {len(found - known)} unmapped; {len(known - found)} removed")
    return int(bool(failures or found != known or schema["version"] != mapping["cliVersion"]))


if __name__ == "__main__":
    raise SystemExit(main())
