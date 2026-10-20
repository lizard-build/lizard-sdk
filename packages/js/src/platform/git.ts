import { handleApiError } from '../errors'
import type { ConnectionConfig } from '../config'

/**
 * Lizard Git (git.lizard.build): repositories, issues, pull requests, reviews, Actions-style
 * CI, releases, webhooks, branch protection and the rest, with the same API key as the rest
 * of the SDK. The key must be a whole account's (no scopes): Lizard Git refuses scoped keys.
 *
 * Repositories are named `"owner/name"`.
 *
 * ```ts
 * const lizard = new Lizard()
 * const repo = await lizard.git.repos.create({ name: 'app', private: true, readme: true })
 * await lizard.git.repos.commitFiles('me/app', { branch: 'main', message: 'Add CI',
 *   files: [{ path: '.lizard/workflows/ci.yml', content: 'on: push\njobs: ...' }] })
 * const pr = await lizard.git.pulls.create('me/app', { title: 'Feature', head: 'feature', base: 'main' })
 * ```
 */

export const DEFAULT_GIT_URL = 'https://git.lizard.build'

export type RepoRef = string
export type Role = 'read' | 'write' | 'admin'

export interface Repo {
  id: number; owner: string; ownerAvatar: string; name: string; description: string; private: boolean
  defaultBranch: string; stars: number; pushedAt: number | null; createdAt: number; updatedAt: number
}
export interface RepoMeta {
  repo: Repo; role: 'owner' | Role | ''; canPush: boolean; canAdmin: boolean; starred: boolean; empty: boolean
  cloneUrl: string; branches: number; tags: number; openIssues: number; openPulls: number
  forkOf: string | null; forks: number
}
export interface Ref { name: string; sha: string; kind: 'branch' | 'tag'; date: number; subject: string; author: string; ahead?: number; behind?: number }
export interface Commit {
  sha: string; parents: string[]; authorName: string; authorEmail: string; date: number
  committerName: string; committerDate: number; subject: string; body?: string
}
export interface TreeEntry { name: string; path: string; type: 'blob' | 'tree' | 'commit'; mode: string; size?: number }
export interface Blob { commit: string; path: string; size: number; content?: string; binary?: boolean; tooLarge?: boolean; lastCommit?: Commit }
export interface FileChange {
  path: string
  /** Text, or base64 when `base64` is true. Leave out with `delete`. */
  content?: string
  base64?: boolean
  delete?: boolean
  /** Rename: the old path (its content moves unless `content` is given). */
  moveFrom?: string
}
export interface CommitFilesOpts {
  branch: string
  message: string
  files: FileChange[]
  /** The commit the branch must still point at (compare-and-swap); a moved branch answers 409. */
  expect?: string
  /** Create `branch` from this ref when it doesn't exist yet. */
  createFrom?: string
  /** Same key, same result: a retried call doesn't commit twice. */
  idempotencyKey?: string
}
export interface Label { id: number; name: string; color: string; description: string }
export interface Assignee { login: string; avatarUrl: string }
export interface Issue {
  number: number; title: string; body: string; state: 'open' | 'closed' | 'merged'; isPull: boolean
  headRef?: string; baseRef?: string; headRepo?: string; mergedSha?: string; draft: boolean
  author: string; authorAvatar: string; comments: number; labels: Label[]; assignees: Assignee[]
  closedAt: number | null; createdAt: number; updatedAt: number
}
export interface IssueDetail {
  issue: Issue; comments: Array<{ id: number; kind: string; author: string; body: string; createdAt: number; [k: string]: unknown }>
  canEdit: boolean; canMerge: boolean
  /** Pull requests: head commit, merge check, what branch protection still needs. */
  pull?: { headSha?: string; baseExists: boolean; headExists: boolean; commits?: number; merge?: unknown; gate?: unknown; reviewRequests: unknown[] }
}
export interface IssueList { items: Issue[]; open: number; closed: number }
export interface ListIssuesOpts { state?: 'open' | 'closed' | 'all'; q?: string; label?: string; assignee?: string }
export interface CreatePullOpts {
  title: string; body?: string
  /** A branch here, or `"owner:branch"` of a fork. */
  head: string
  base?: string
  /** `"owner/name"` of the fork `head` is on (instead of `owner:branch`). */
  headRepo?: string
  draft?: boolean
  reviewers?: string[]
}
export interface UpdateIssueOpts {
  title?: string; body?: string; state?: 'open' | 'closed'
  labels?: string[]; assignees?: string[]
  /** Pull requests only. */
  reviewers?: string[]; draft?: boolean
}
export interface MergeOpts { method?: 'merge' | 'squash' | 'rebase'; message?: string; deleteBranch?: boolean; bypass?: boolean }
export interface LineComment { path: string; line: number; side?: 'RIGHT' | 'LEFT'; body: string }
export interface ReviewOpts { event: 'APPROVE' | 'REQUEST_CHANGES' | 'COMMENT'; body?: string; comments?: LineComment[] }
export interface Run {
  id: number; number: number; workflow: string; name: string; event: string; ref: string; sha: string
  actor: string; status: string; title: string; createdAt: number; startedAt: number | null; finishedAt: number | null
  jobs: Job[]
}
export interface Job {
  id: number; key: string; name: string; status: string; image: string
  steps: Array<{ name: string; status: string }> | null; logSize: number; startedAt: number | null; finishedAt: number | null
}
export interface ListRunsOpts { branch?: string; sha?: string; workflow?: string; status?: string; pr?: number; page?: number }
export interface LogChunk { offset: number; next: number; size: number; text: string; done: boolean }
export interface Workflow { path: string; name: string; events: string[]; dispatch: boolean }
export interface Artifact { name: string; size: number; job: string; createdAt: number }
export interface Collaborator { login: string; name: string; avatarUrl: string; role: Role; createdAt: number }
export interface Invitation { id: number; repo: string; owner: string; login?: string; role: Role; inviter: string; createdAt: number; expiresAt: number }
export interface Webhook {
  id: number; url: string; contentType: 'json' | 'form'; events: string[]; active: boolean; hasSecret: boolean
  lastStatus: number; lastError?: string; lastDeliveryAt: number | null; createdAt: number
}
export interface WebhookOpts { url?: string; secret?: string; contentType?: 'json' | 'form'; events?: string[]; active?: boolean }
export interface Delivery { id: number; event: string; status: number; error?: string; durationMs: number; createdAt: number; [k: string]: unknown }
export interface BranchRule {
  id: number; pattern: string; requirePullRequest: boolean; requiredApprovals: number; requiredChecks: string[]
  blockForcePush: boolean; blockDeletion: boolean; enforceAdmins: boolean; requireCodeOwners: boolean; createdAt: number
}
export type BranchRuleOpts = Partial<Omit<BranchRule, 'id' | 'createdAt'>>
export interface Release {
  id: number; tag: string; target: string; sha: string; name: string; body: string; draft: boolean; prerelease: boolean
  author: string; createdAt: number; assets: Array<{ id: number; name: string; size: number; contentType: string; downloads?: number }>
}
export interface ReleaseOpts { tag: string; target?: string; name?: string; body?: string; draft?: boolean; prerelease?: boolean }
export interface CommitStatus { state: 'pending' | 'success' | 'failure' | 'error'; context: string; description?: string; target_url?: string }
export interface CombinedStatus { sha: string; state: string; total_count: number; statuses: Array<CommitStatus & { createdAt: number; creator: string }> }
export interface Notification { id: number; reason: string; repo: string; number: number; title: string; actor: string; url: string; unread: boolean; updatedAt: number }
export interface Token { id: number; name: string; repos: string[]; refs: string[]; paths: string[]; readOnly: boolean; createdAt: number; lastUsedAt: number | null }
export interface TokenOpts { name: string; repos?: string[]; refs?: string[]; paths?: string[]; readOnly?: boolean }
export interface GitUser { id: number; login: string; name: string; avatarUrl: string; bio: string; createdAt: number }

const seg = encodeURIComponent
function qs(path: string, values: Record<string, string | number | boolean | undefined>): string {
  const q = new URLSearchParams()
  for (const [k, v] of Object.entries(values)) if (v !== undefined && v !== '') q.set(k, String(v))
  return q.size ? `${path}?${q}` : path
}
/** A branch or file path, each part escaped; . and .. parts refused (they'd reach other API paths). */
function segs(p: string): string {
  const parts = p.split('/')
  if (parts.some(x => x === '' || x === '.' || x === '..')) throw new Error(`bad path: "${p}"`)
  return parts.map(seg).join('/')
}
function repoPath(repo: RepoRef): string {
  const m = /^([^/\s]+)\/([^/\s]+?)(\.git)?$/.exec(repo)
  if (!m || [m[1], m[2]].some(x => x === '.' || x === '..')) throw new Error(`repository must be "owner/name", got "${repo}"`)
  return `/api/repos/${seg(m[1])}/${seg(m[2])}`
}

/** HTTP to Lizard Git with the connection's API key. */
export class GitClient {
  readonly url: string
  constructor(readonly config: ConnectionConfig, url?: string) {
    this.url = (url ?? process.env.LIZARD_GIT_URL ?? DEFAULT_GIT_URL).replace(/\/+$/, '')
  }
  async raw(method: string, path: string, body?: BodyInit, headers: Record<string, string> = {}): Promise<Response> {
    const res = await fetch(this.url + path, {
      method, body, headers: { 'X-API-Key': this.config.apiKey, ...headers },
      redirect: 'error', // a redirect would carry the key to wherever it points
      signal: AbortSignal.timeout(this.config.requestTimeoutMs),
    })
    if (!res.ok) await handleApiError(res)
    return res
  }
  async request<T>(method: string, path: string, body?: unknown, headers: Record<string, string> = {}): Promise<T> {
    const res = await this.raw(method, path, body === undefined ? undefined : JSON.stringify(body),
      body === undefined ? headers : { 'Content-Type': 'application/json', ...headers })
    const text = res.status === 204 ? '' : await res.text()
    return (text ? JSON.parse(text) : undefined) as T
  }
  get<T>(path: string): Promise<T> { return this.request('GET', path) }
  post<T>(path: string, body?: unknown): Promise<T> { return this.request('POST', path, body ?? {}) }
  put<T>(path: string, body?: unknown): Promise<T> { return this.request('PUT', path, body ?? {}) }
  patch<T>(path: string, body: unknown): Promise<T> { return this.request('PATCH', path, body) }
  delete<T = void>(path: string): Promise<T> { return this.request('DELETE', path) }
  async bytes(path: string): Promise<Uint8Array> { return new Uint8Array(await (await this.raw('GET', path)).arrayBuffer()) }
}

export class GitReposAPI {
  constructor(private readonly c: GitClient) {}
  /** Yours and the ones you collaborate on by default; `owner`, `q`, `starred` narrow it. */
  list(opts: { owner?: string; member?: string; starred?: string; q?: string; sort?: 'updated' | 'stars' | 'name' } = {}): Promise<Repo[]> {
    return this.c.get(qs('/api/repos', opts))
  }
  /** Answers the new repository's `owner` and `name`. */
  create(opts: { name: string; description?: string; private?: boolean; readme?: boolean; defaultBranch?: string }): Promise<{ owner: string; name: string }> {
    return this.c.post('/api/repos', opts)
  }
  get(repo: RepoRef): Promise<RepoMeta> { return this.c.get(repoPath(repo)) }
  update(repo: RepoRef, opts: { name?: string; description?: string; private?: boolean; defaultBranch?: string }): Promise<{ ok: boolean }> {
    return this.c.patch(repoPath(repo), opts)
  }
  delete(repo: RepoRef): Promise<void> { return this.c.delete(repoPath(repo)) }
  star(repo: RepoRef): Promise<void> { return this.c.put(`${repoPath(repo)}/star`) }
  unstar(repo: RepoRef): Promise<void> { return this.c.delete(`${repoPath(repo)}/star`) }
  /** Fork into your account (`name` defaults to the same name). */
  fork(repo: RepoRef, opts: { name?: string } = {}): Promise<{ owner: string; name: string }> { return this.c.post(`${repoPath(repo)}/forks`, opts) }
  forks(repo: RepoRef): Promise<Repo[]> { return this.c.get(`${repoPath(repo)}/forks`) }
  /** Branches and tags. */
  refs(repo: RepoRef): Promise<Ref[]> { return this.c.get(`${repoPath(repo)}/refs`) }
  createBranch(repo: RepoRef, name: string, from?: string): Promise<{ name: string; sha: string }> { return this.c.post(`${repoPath(repo)}/branches`, { name, from }) }
  deleteBranch(repo: RepoRef, name: string): Promise<void> { return this.c.delete(`${repoPath(repo)}/branches/${segs(name)}`) }
  tree(repo: RepoRef, opts: { ref?: string; path?: string } = {}): Promise<{ commit: string; path: string; entries: TreeEntry[] }> {
    return this.c.get(qs(`${repoPath(repo)}/tree`, opts))
  }
  /** A file as JSON (text in `content`). */
  file(repo: RepoRef, path: string, ref?: string): Promise<Blob> { return this.c.get(qs(`${repoPath(repo)}/blob`, { path, ref })) }
  /** A file's bytes, whatever its size or type. */
  raw(repo: RepoRef, path: string, ref: string): Promise<Uint8Array> {
    repoPath(repo)
    const [owner, name] = repo.split('/')
    return this.c.bytes(`/raw/${seg(owner)}/${seg(name)}/${segs(ref)}/${segs(path)}`)
  }
  /** Every file path at a ref. */
  files(repo: RepoRef, ref?: string): Promise<string[]> { return this.c.get(qs(`${repoPath(repo)}/files`, { ref })) }
  search(repo: RepoRef, q: string, ref?: string): Promise<unknown> { return this.c.get(qs(`${repoPath(repo)}/search`, { q, ref })) }
  commits(repo: RepoRef, opts: { ref?: string; path?: string; page?: number } = {}): Promise<{ commits: Commit[]; more: boolean }> {
    return this.c.get(qs(`${repoPath(repo)}/commits`, opts))
  }
  commit(repo: RepoRef, sha: string): Promise<{ commit: Commit; diff: unknown }> { return this.c.get(`${repoPath(repo)}/commits/${seg(sha)}`) }
  compare(repo: RepoRef, base: string, head: string): Promise<unknown> { return this.c.get(qs(`${repoPath(repo)}/compare`, { base, head })) }
  /** Commit files on the server: no clone, no push. Answers 409 when `expect` no longer matches. */
  commitFiles(repo: RepoRef, opts: CommitFilesOpts): Promise<{ sha: string; branch: string; [k: string]: unknown }> {
    const { idempotencyKey, ...body } = opts
    return this.c.request('POST', `${repoPath(repo)}/commits`, body, idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : {})
  }
  /** Rebase `head` (branch or commit) onto `onto` on the server and move `onto` there; retried on races. */
  land(repo: RepoRef, opts: { head: string; onto: string; deleteHead?: boolean }): Promise<{ sha: string; [k: string]: unknown }> {
    return this.c.post(`${repoPath(repo)}/land`, opts)
  }
  /** Who moved which branch, when. */
  reflog(repo: RepoRef, ref?: string): Promise<unknown[]> { return this.c.get(qs(`${repoPath(repo)}/reflog`, { ref })) }
  archive(repo: RepoRef, ref: string, format: 'zip' | 'tar.gz' = 'tar.gz'): Promise<Uint8Array> {
    return this.c.bytes(`${repoPath(repo)}/archive/${seg(ref)}.${format}`)
  }
  /**
   * The HTTPS clone URL. With `withKey`, it carries the API key, so plain `git clone` works
   * without a helper; git then keeps it in .git/config. For anything shared or logged, use a
   * limited Lizard Git token (`tokens.create`) as `apiKey` instead of the account's key.
   */
  cloneUrl(repo: RepoRef, opts: { withKey?: boolean } = {}): string {
    repoPath(repo)
    const u = new URL(`${this.c.url}/${repo.replace(/\.git$/, '')}.git`)
    if (opts.withKey) { u.username = 'lizard'; u.password = this.c.config.apiKey }
    return u.toString()
  }
}

export class GitIssuesAPI {
  constructor(protected readonly c: GitClient, private readonly pulls = false) {}
  protected base(repo: RepoRef) { return `${repoPath(repo)}/issues` }
  list(repo: RepoRef, opts: ListIssuesOpts = {}): Promise<IssueList> {
    return this.c.get(qs(this.base(repo), { ...opts, pulls: this.pulls ? 1 : undefined }))
  }
  get(repo: RepoRef, number: number): Promise<IssueDetail> { return this.c.get(`${this.base(repo)}/${number}`) }
  update(repo: RepoRef, number: number, opts: UpdateIssueOpts): Promise<{ ok: boolean }> { return this.c.patch(`${this.base(repo)}/${number}`, opts) }
  comment(repo: RepoRef, number: number, body: string): Promise<{ id: number }> { return this.c.post(`${this.base(repo)}/${number}/comments`, { body }) }
  close(repo: RepoRef, number: number): Promise<{ ok: boolean }> { return this.update(repo, number, { state: 'closed' }) }
  reopen(repo: RepoRef, number: number): Promise<{ ok: boolean }> { return this.update(repo, number, { state: 'open' }) }
}

export class GitIssuesOnlyAPI extends GitIssuesAPI {
  constructor(c: GitClient) { super(c, false) }
  create(repo: RepoRef, opts: { title: string; body?: string }): Promise<{ number: number }> { return this.c.post(this.base(repo), opts) }
}

export class GitPullsAPI extends GitIssuesAPI {
  constructor(c: GitClient) { super(c, true) }
  create(repo: RepoRef, opts: CreatePullOpts): Promise<{ number: number }> { return this.c.post(this.base(repo), opts) }
  /** Mark a draft ready for review. */
  ready(repo: RepoRef, number: number): Promise<{ ok: boolean }> { return this.update(repo, number, { draft: false }) }
  merge(repo: RepoRef, number: number, opts: MergeOpts = {}): Promise<{ sha: string }> {
    return this.c.post(`${repoPath(repo)}/pulls/${number}/merge`, opts)
  }
  diff(repo: RepoRef, number: number): Promise<unknown> { return this.c.get(`${repoPath(repo)}/pulls/${number}/diff`) }
  commits(repo: RepoRef, number: number): Promise<Commit[]> { return this.c.get(`${repoPath(repo)}/pulls/${number}/commits`) }
  reviews(repo: RepoRef, number: number): Promise<{ reviews: unknown[]; comments: unknown[]; decision: { approvals: string[]; changesRequested: string[] } }> {
    return this.c.get(`${repoPath(repo)}/pulls/${number}/reviews`)
  }
  review(repo: RepoRef, number: number, opts: ReviewOpts): Promise<{ id: number; state: string }> { return this.c.post(`${repoPath(repo)}/pulls/${number}/reviews`, opts) }
  approve(repo: RepoRef, number: number, body = ''): Promise<{ id: number; state: string }> { return this.review(repo, number, { event: 'APPROVE', body }) }
  requestChanges(repo: RepoRef, number: number, body: string): Promise<{ id: number; state: string }> { return this.review(repo, number, { event: 'REQUEST_CHANGES', body }) }
  lineComment(repo: RepoRef, number: number, c: LineComment): Promise<{ id: number }> { return this.c.post(`${repoPath(repo)}/pulls/${number}/comments`, c) }
  deleteLineComment(repo: RepoRef, number: number, id: number): Promise<void> { return this.c.delete(`${repoPath(repo)}/pulls/${number}/comments/${id}`) }
  /** The combined commit status of the pull request's head (CI and external checks). */
  async checks(repo: RepoRef, number: number): Promise<CombinedStatus> {
    const { pull } = await this.get(repo, number)
    if (!pull?.headSha) throw new Error(`pull request #${number} has no head commit`)
    return this.c.get(`${repoPath(repo)}/commits/${pull.headSha}/status`)
  }
}

export class GitSecretsAPI {
  constructor(private readonly c: GitClient) {}
  list(repo: RepoRef): Promise<{ configured: boolean; secrets: Array<{ name: string; updatedAt: number }> }> { return this.c.get(`${repoPath(repo)}/actions/secrets`) }
  set(repo: RepoRef, name: string, value: string): Promise<void> { return this.c.put(`${repoPath(repo)}/actions/secrets/${seg(name)}`, { value }) }
  delete(repo: RepoRef, name: string): Promise<void> { return this.c.delete(`${repoPath(repo)}/actions/secrets/${seg(name)}`) }
}

export class GitActionsAPI {
  readonly secrets: GitSecretsAPI
  constructor(private readonly c: GitClient) { this.secrets = new GitSecretsAPI(c) }
  runs(repo: RepoRef, opts: ListRunsOpts = {}): Promise<{ runs: Run[]; more: boolean }> { return this.c.get(qs(`${repoPath(repo)}/actions/runs`, { ...opts })) }
  run(repo: RepoRef, number: number): Promise<Run> { return this.c.get(`${repoPath(repo)}/actions/runs/${number}`) }
  cancel(repo: RepoRef, number: number): Promise<void> { return this.c.post(`${repoPath(repo)}/actions/runs/${number}/cancel`) }
  /** Run the same workflow at the same commit again (a new run). */
  rerun(repo: RepoRef, number: number): Promise<{ number: number }> { return this.c.post(`${repoPath(repo)}/actions/runs/${number}/rerun`) }
  /** Let a run from a fork's pull request start (it waits for someone with write access). */
  approve(repo: RepoRef, number: number): Promise<void> { return this.c.post(`${repoPath(repo)}/actions/runs/${number}/approve`) }
  /** Part of a job's log from `offset`; follow `next` until `done`. */
  log(repo: RepoRef, jobId: number, offset = 0): Promise<LogChunk> { return this.c.get(qs(`${repoPath(repo)}/actions/jobs/${jobId}/log`, { offset })) }
  async fullLog(repo: RepoRef, jobId: number): Promise<string> {
    return new TextDecoder().decode(await this.c.bytes(`${repoPath(repo)}/actions/jobs/${jobId}/log.txt`))
  }
  /** Each new piece of the log as it's written, until the job ends. */
  async *followLog(repo: RepoRef, jobId: number, opts: { intervalMs?: number; signal?: AbortSignal } = {}): AsyncGenerator<string> {
    let offset = 0
    while (!opts.signal?.aborted) {
      const chunk = await this.log(repo, jobId, offset)
      if (chunk.text) yield chunk.text
      offset = chunk.next
      if (chunk.done && offset >= chunk.size) return
      if (!chunk.text) await new Promise(r => setTimeout(r, opts.intervalMs ?? 1500))
    }
  }
  /** Wait until the run ends (success, failure, cancelled, ...). */
  async wait(repo: RepoRef, number: number, opts: { timeoutMs?: number; intervalMs?: number } = {}): Promise<Run> {
    const until = Date.now() + (opts.timeoutMs ?? 30 * 60_000)
    for (;;) {
      const run = await this.run(repo, number)
      if (!['queued', 'running', 'waiting', 'pending'].includes(run.status)) return run
      if (Date.now() > until) throw new Error(`run ${number} is still ${run.status}`)
      await new Promise(r => setTimeout(r, opts.intervalMs ?? 3000))
    }
  }
  artifacts(repo: RepoRef, number: number): Promise<Artifact[]> { return this.c.get(`${repoPath(repo)}/actions/runs/${number}/artifacts`) }
  /** An artifact as a .tar.gz. */
  downloadArtifact(repo: RepoRef, number: number, name: string): Promise<Uint8Array> { return this.c.bytes(`${repoPath(repo)}/actions/runs/${number}/artifacts/${seg(name)}`) }
  workflows(repo: RepoRef): Promise<{ enabled: boolean; reason?: string; workflows: Workflow[] }> { return this.c.get(`${repoPath(repo)}/actions/workflows`) }
  /** Start a workflow that has `on: workflow_dispatch`. */
  dispatch(repo: RepoRef, opts: { workflow: string; ref?: string; inputs?: Record<string, string> }): Promise<{ number: number }> {
    return this.c.post(`${repoPath(repo)}/actions/workflows/dispatch`, opts)
  }
  /** Latest run status per commit, for the given commits. */
  status(repo: RepoRef, shas: string[]): Promise<Record<string, string>> { return this.c.get(qs(`${repoPath(repo)}/actions/status`, { shas: shas.join(',') })) }
}

export class GitCollaboratorsAPI {
  constructor(private readonly c: GitClient) {}
  list(repo: RepoRef): Promise<{ collaborators: Collaborator[]; invitations: Invitation[]; role: string }> { return this.c.get(`${repoPath(repo)}/collaborators`) }
  /** Invite someone with a Lizard Git account (they sign in once first); they're in once they accept. */
  invite(repo: RepoRef, login: string, role: Role = 'write'): Promise<{ login: string; role: Role; status: 'invited' | 'updated' }> { return this.c.post(`${repoPath(repo)}/collaborators`, { login, role }) }
  setRole(repo: RepoRef, login: string, role: Role): Promise<{ login: string; role: Role }> { return this.c.patch(`${repoPath(repo)}/collaborators/${seg(login)}`, { role }) }
  /** Remove someone (or yourself: leave). */
  remove(repo: RepoRef, login: string): Promise<void> { return this.c.delete(`${repoPath(repo)}/collaborators/${seg(login)}`) }
  cancelInvitation(repo: RepoRef, id: number): Promise<void> { return this.c.delete(`${repoPath(repo)}/invitations/${id}`) }
  /** Invitations waiting for you. */
  invitations(): Promise<Invitation[]> { return this.c.get('/api/user/invitations') }
  accept(id: number): Promise<void> { return this.c.post(`/api/user/invitations/${id}/accept`) }
  decline(id: number): Promise<void> { return this.c.post(`/api/user/invitations/${id}/decline`) }
}

export class GitWebhooksAPI {
  constructor(private readonly c: GitClient) {}
  list(repo: RepoRef): Promise<{ hooks: Webhook[]; events: string[] }> { return this.c.get(`${repoPath(repo)}/hooks`) }
  /** GitHub-style payloads, signed with `X-Hub-Signature-256` when there's a secret. */
  create(repo: RepoRef, opts: WebhookOpts & { url: string }): Promise<Webhook> { return this.c.post(`${repoPath(repo)}/hooks`, opts) }
  get(repo: RepoRef, id: number): Promise<Webhook> { return this.c.get(`${repoPath(repo)}/hooks/${id}`) }
  update(repo: RepoRef, id: number, opts: WebhookOpts): Promise<Webhook> { return this.c.patch(`${repoPath(repo)}/hooks/${id}`, opts) }
  delete(repo: RepoRef, id: number): Promise<void> { return this.c.delete(`${repoPath(repo)}/hooks/${id}`) }
  ping(repo: RepoRef, id: number): Promise<void> { return this.c.post(`${repoPath(repo)}/hooks/${id}/pings`) }
  deliveries(repo: RepoRef, id: number): Promise<Delivery[]> { return this.c.get(`${repoPath(repo)}/hooks/${id}/deliveries`) }
  delivery(repo: RepoRef, id: number, deliveryId: number): Promise<Delivery> { return this.c.get(`${repoPath(repo)}/hooks/${id}/deliveries/${deliveryId}`) }
  redeliver(repo: RepoRef, id: number, deliveryId: number): Promise<void> { return this.c.post(`${repoPath(repo)}/hooks/${id}/deliveries/${deliveryId}/redeliver`) }
}

export class GitBranchRulesAPI {
  constructor(private readonly c: GitClient) {}
  list(repo: RepoRef): Promise<BranchRule[]> { return this.c.get(`${repoPath(repo)}/branch-rules`) }
  create(repo: RepoRef, opts: BranchRuleOpts & { pattern: string }): Promise<BranchRule> { return this.c.post(`${repoPath(repo)}/branch-rules`, opts) }
  update(repo: RepoRef, id: number, opts: BranchRuleOpts): Promise<BranchRule> { return this.c.patch(`${repoPath(repo)}/branch-rules/${id}`, opts) }
  delete(repo: RepoRef, id: number): Promise<void> { return this.c.delete(`${repoPath(repo)}/branch-rules/${id}`) }
}

export class GitLabelsAPI {
  constructor(private readonly c: GitClient) {}
  list(repo: RepoRef): Promise<Label[]> { return this.c.get(`${repoPath(repo)}/labels`) }
  create(repo: RepoRef, opts: { name: string; color?: string; description?: string }): Promise<Label> { return this.c.post(`${repoPath(repo)}/labels`, opts) }
  update(repo: RepoRef, name: string, opts: { name?: string; color?: string; description?: string }): Promise<Label> { return this.c.patch(`${repoPath(repo)}/labels/${seg(name)}`, opts) }
  delete(repo: RepoRef, name: string): Promise<void> { return this.c.delete(`${repoPath(repo)}/labels/${seg(name)}`) }
}

export class GitReleasesAPI {
  constructor(private readonly c: GitClient) {}
  list(repo: RepoRef): Promise<Release[]> { return this.c.get(`${repoPath(repo)}/releases`) }
  /** Creates the tag too when it doesn't exist (at `target`, default branch by default). */
  create(repo: RepoRef, opts: ReleaseOpts): Promise<Release> { return this.c.post(`${repoPath(repo)}/releases`, opts) }
  get(repo: RepoRef, id: number): Promise<Release> { return this.c.get(`${repoPath(repo)}/releases/${id}`) }
  getByTag(repo: RepoRef, tag: string): Promise<Release> { return this.c.get(`${repoPath(repo)}/releases/tags/${seg(tag)}`) }
  update(repo: RepoRef, id: number, opts: { name?: string; body?: string; draft?: boolean; prerelease?: boolean }): Promise<Release> {
    return this.c.patch(`${repoPath(repo)}/releases/${id}`, opts)
  }
  delete(repo: RepoRef, id: number): Promise<void> { return this.c.delete(`${repoPath(repo)}/releases/${id}`) }
  async uploadAsset(repo: RepoRef, id: number, name: string, data: Uint8Array | Blob | string, contentType = 'application/octet-stream'): Promise<{ id: number; name: string; size: number; contentType: string }> {
    const body: BodyInit = typeof data === 'string' || data instanceof Blob ? data : new Blob([new Uint8Array(data as Uint8Array)])
    const res = await this.c.raw('POST', qs(`${repoPath(repo)}/releases/${id}/assets`, { name }), body, { 'Content-Type': contentType })
    return res.json() as Promise<{ id: number; name: string; size: number; contentType: string }>
  }
  downloadAsset(repo: RepoRef, id: number, assetId: number): Promise<Uint8Array> { return this.c.bytes(`${repoPath(repo)}/releases/${id}/assets/${assetId}`) }
  deleteAsset(repo: RepoRef, id: number, assetId: number): Promise<void> { return this.c.delete(`${repoPath(repo)}/releases/${id}/assets/${assetId}`) }
}

export class GitStatusesAPI {
  constructor(private readonly c: GitClient) {}
  /** Report a check on a commit (what required checks in branch rules wait for). */
  create(repo: RepoRef, sha: string, status: CommitStatus): Promise<unknown> { return this.c.post(`${repoPath(repo)}/statuses/${seg(sha)}`, status) }
  list(repo: RepoRef, ref: string): Promise<unknown[]> { return this.c.get(`${repoPath(repo)}/commits/${seg(ref)}/statuses`) }
  combined(repo: RepoRef, ref: string): Promise<CombinedStatus> { return this.c.get(`${repoPath(repo)}/commits/${seg(ref)}/status`) }
}

export class GitNotificationsAPI {
  constructor(private readonly c: GitClient) {}
  list(opts: { all?: boolean } = {}): Promise<{ notifications: Notification[]; unread: number }> { return this.c.get(qs('/api/notifications', { all: opts.all ? 1 : undefined })) }
  markRead(ids?: number[]): Promise<void> { return this.c.post('/api/notifications/read', ids?.length ? { ids } : { all: true }) }
}

export class GitTokensAPI {
  constructor(private readonly c: GitClient) {}
  list(): Promise<Token[]> { return this.c.get('/api/user/tokens') }
  /** A Lizard Git token (lzg_...), optionally limited to repos, refs, paths, or read-only. The secret is in `token`, once. */
  create(opts: TokenOpts): Promise<{ id: number; name: string; token: string }> { return this.c.post('/api/user/tokens', opts) }
  delete(id: number): Promise<void> { return this.c.delete(`/api/user/tokens/${id}`) }
}

/** `lizard.git`: everything Lizard Git does, with the client's API key. */
export class GitAPI {
  readonly client: GitClient
  readonly repos: GitReposAPI
  readonly issues: GitIssuesOnlyAPI
  readonly pulls: GitPullsAPI
  readonly actions: GitActionsAPI
  readonly collaborators: GitCollaboratorsAPI
  readonly webhooks: GitWebhooksAPI
  readonly branchRules: GitBranchRulesAPI
  readonly labels: GitLabelsAPI
  readonly releases: GitReleasesAPI
  readonly statuses: GitStatusesAPI
  readonly notifications: GitNotificationsAPI
  readonly tokens: GitTokensAPI
  constructor(config: ConnectionConfig, url?: string) {
    const c = this.client = new GitClient(config, url)
    this.repos = new GitReposAPI(c)
    this.issues = new GitIssuesOnlyAPI(c)
    this.pulls = new GitPullsAPI(c)
    this.actions = new GitActionsAPI(c)
    this.collaborators = new GitCollaboratorsAPI(c)
    this.webhooks = new GitWebhooksAPI(c)
    this.branchRules = new GitBranchRulesAPI(c)
    this.labels = new GitLabelsAPI(c)
    this.releases = new GitReleasesAPI(c)
    this.statuses = new GitStatusesAPI(c)
    this.notifications = new GitNotificationsAPI(c)
    this.tokens = new GitTokensAPI(c)
  }
  /** Who the key signs in as on Lizard Git. */
  me(): Promise<GitUser> { return this.client.get('/api/session') }
  user(login: string): Promise<{ user: GitUser; starred: Repo[] }> { return this.client.get(`/api/users/${seg(login)}`) }
}
