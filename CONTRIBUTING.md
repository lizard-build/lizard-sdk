# Contributing

## Setup

Use Node.js 22+ and Python 3.10+ for development. The published JavaScript client supports Node.js 18+; the current test tools require a newer Node.js version.

```sh
npm install -g npm@11.18.0
npm install
python3 -m venv .venv
.venv/bin/python -m pip install -e './packages/python[dev]' build
```

## Checks

```sh
npm test
npm run lint
npm run build
.venv/bin/python -m pytest packages/python/tests tests
.venv/bin/python -m build packages/python
```

Most tests use mock HTTP responses, including shared contracts in `tests/contracts/platform.json`. The node-agent tests skip by default. They need `LIZARD_LIVE_TESTS=1` and `ADMIN_SECRET` on an approved test host, and create and kill sandboxes. Passing mock tests does not prove live platform behavior.

The optional CLI discovery audit needs Lizard CLI 4.0.77, the version pinned in `tests/contracts/cli-coverage.json`:

```sh
python3 scripts/audit_cli.py --output cli-audit.json
```

It checks command discovery, not the live effect of each command.

## Documentation

Keep the root README short. Put language-specific setup in `packages/js/README.md` and `packages/python/README.md`, and shared behavior in `docs/`. Package releases use each package's own README.

When product facts change, update the root README and both package READMEs together. Keep product names, use cases, billing terms, runtime limits, links and package descriptions consistent; use each language's own method names and examples. Check that the npm tarball and Python distributions include the intended README and metadata before publishing.

Use examples that check results and clean up sandboxes with `try/finally` or a Python context manager. Check examples against the public exports and method signatures. Describe runtime support as it exists: Firecracker microVM sandboxes, persistent files on volumes that can grow but not shrink, pause/resume that keeps memory and processes, snapshots (ready in about 2 s, restore in about 0.4 s) and fork; file watching and log streaming are not available yet.

## Releases

A push to `main` starts auto-tagging, followed by npm and PyPI publishing. Use a branch and pull request for changes that still need review. Changes to a package README or package metadata reach registries only after a release.
