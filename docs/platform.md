# Platform guide

[Sandbox reference](sandboxes.md) · [CLI coverage and migration](cli-parity.md)

Use `Lizard` to manage cloud apps, databases, storage, projects and credentials. Platform methods do not require a default project; pass resource IDs to each method.

```ts
import { Lizard } from '@lizard-build/sdk'

const lizard = new Lizard({})
const projects = await lizard.projects.list()
console.log(projects.map(project => ({ id: project.id, name: project.name })))
```

```python
from lizard import Lizard

lizard = Lizard()
for project in lizard.projects.list():
    print(project.id, project.name)
```

Both clients read `LIZARD_API_KEY`. To create sandboxes or use project-bound volumes, pass `project` to `Lizard`.

## API namespaces

| TypeScript | Python | Purpose |
| --- | --- | --- |
| `projects` | `projects` | Projects, config, services and project logs |
| `services` | `services` | Deploy, inspect, scale and run commands in apps |
| `addons` | `addons` | Managed databases and other addons |
| `secrets` | `secrets` | Environment variables and secret references |
| `domains` | `domains` | App domains and DNS verification |
| `storage` | `storage` | S3 object listing and uploads |
| `github` | `github` | GitHub connection status and checkout |
| `metrics` | `metrics` | Resource use and project costs |
| `workspaces` | `workspaces` | Workspaces and resource ownership |
| `apiKeys` | `api_keys` | API keys and scopes |
| `regions` | `regions` | Available regions |
| `billing` | `billing` | Account balance, transactions and payments |
| `volumes` | `volumes` | Persistent files for sandboxes in the client's project |

`whoami()` returns the account identity visible to the credential. `platform` exposes the underlying HTTP client for endpoints without a dedicated method. See [CLI coverage](cli-parity.md#native-apis) for the method map.

## Workspaces and scoped keys

For an application with separate users, you can create a workspace and project for each user, then issue a key scoped to that workspace. Run this from your trusted application server with a key that has access to create these resources.

```ts
import { Lizard } from '@lizard-build/sdk'

const lizard = new Lizard({})
const workspace = await lizard.workspaces.create({ name: 'example-user' })
const project = await lizard.projects.create({ workspaceId: workspace.id, name: 'default' })
const key = await lizard.apiKeys.create({
  name: 'example-user',
  workspaces: [workspace.id],
})
// Store key.key in your secret store now; the API returns it only once.
```

```python
from lizard import Lizard

lizard = Lizard()
workspace = lizard.workspaces.create(name="example-user")
project = lizard.projects.create(workspace_id=workspace.id, name="default")
key = lizard.api_keys.create(name="example-user", workspaces=[workspace.id])
# Store key.key in your secret store now; the API returns it only once.
```

A key with no scopes has access to all resources the creating account can reach. Pass `workspaces` or `projects` to limit that access. Scoped keys cannot create broader keys.

If tools inside a sandbox need Lizard access, pass a scoped key through `lizardToken` / `lizard_token`. Any code in that sandbox can read the key and use its permissions. Choose a template with the CLI installed when running CLI commands.

### Account and billing access

Billing belongs to the account, across all its workspaces. Scoped keys cannot access account billing or account-wide usage; those routes return HTTP 403 with `ACCOUNT_SCOPE_REQUIRED`. Their `whoami()` response includes identity and scopes, without the account's email, balance or plan. Use scoped `metrics` calls for project costs.

`workspaces.delete()` requires an empty workspace by default. The `force` option removes the workspace and its resources. Revoking a key or deleting a resource takes effect immediately.

## Optional CLI adapter

Native HTTP methods do not need the CLI. `LizardCLI` supports local workflows such as linking a directory or running CLI commands. Install Lizard CLI 4.0.8+ on `PATH` before using it. The x402 payment helper also needs the CLI.

See [CLI adapter usage](cli-parity.md#optional-cli-adapter) and [payment behavior](cli-parity.md#x402). For config changes, inspect `ConfigApplyError.result` before retrying: the server may have saved the config even if a deploy or restart failed.
