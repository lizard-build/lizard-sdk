export { Lizard } from './lizard'
export type { LizardOpts, Account } from './lizard'
export { Sandbox } from './sandbox'
export type { SandboxOpts, SandboxInfo, SandboxSnapshot, SnapshotOpts, SnapshotWaitOpts, ExposedPort, ForkResult } from './sandbox'
export { resolveProjectId } from './project'
export type { ProcessResult, ProcessOpts, ProcessInfo, ProcessSignal } from './sandbox/process'
export { Desktop } from './sandbox/desktop'
export type { DesktopInfo, DesktopStartOpts, ClickOpts, MouseButton, ScrollDirection } from './sandbox/desktop'
export type { FileInfo, FsOpts, FsEvent } from './sandbox/fs'
export type { ConnectionOpts } from './config'
export {
  LizardError,
  ConfigApplyError,
  AuthenticationError,
  NotFoundError,
  ConflictError,
  TimeoutError,
} from './errors'

export { CodeSandbox } from './code-interpreter'
export type {
  Execution,
  ExecutionError,
  CodeContext,
  RunCodeOpts,
  CreateContextOpts,
  RunCodeLanguage,
} from './code-interpreter'

export { Volume } from './volume'
export type { VolumeInfo, CreateVolumeOpts } from './volume'

// Platform management API
export { DeployHandle } from './platform/services'
export { PlatformClient } from './platform/client'
export {
  WorkspacesAPI, ApiKeysAPI, RegionsAPI, BillingAPI,
  ProjectsAPI, ServicesAPI, AddonsAPI, SecretsAPI, DomainsAPI, MetricsAPI,
} from './platform'
export type {
  Workspace, CreateWorkspaceOpts,
  ApiKey, CreatedApiKey, ApiKeyScope, CreateApiKeyOpts,
  Region,
  Balance, Transaction, TransactionPage, ListTransactionsOpts,
  Project, CreateProjectOpts,
  Service, CreateServiceOpts, ScaleOpts, LogLine, DeployEvent,
  Addon, AddonType, CreateAddonOpts,
  Secret, SetSecretOpts,
  DomainInfo,
  MetricPoint, MetricRange, ServiceMetrics, CostMetrics,
} from './platform'

export { StorageAPI } from './platform/storage'
export { GitHubAPI } from './platform/github'
export type { ServiceUpdate } from './platform/services'
export type { ProjectConfig, ConfigResult } from './platform/projects'
export type { DomainStatus } from './platform/domains'
export type { RawMetrics, ProjectCost } from './platform/metrics'
export type { StreamEvent } from './platform/client'

export { LizardCLI } from './cli'
export type { CLIResult, CLIOptions } from './cli'
