import { messageFrom } from '@/lib/api-error'
import { AuthError, csrfToken } from '@/lib/auth-client'

/**
 * The company itself, and proving the domain it claims.
 *
 * The invitation calls are deliberately **not** here — they already live in
 * `onboarding-client.ts`, and a second copy is how two callers of one endpoint
 * start disagreeing about its shape. This file holds only what had no home:
 * reading the current company, and the two domain-claim calls that `/settings`
 * is built on.
 */

export type CurrentCompany = {
  workspace_id: string
  name: string
  domain: string
  website_url: string | null
  domain_verified: boolean
  role: string
  may_administer: boolean
}

/** The four ways to prove a domain, as `app/connectors/domain_check.py` names them. */
export type ClaimMethod = 'dns_txt' | 'file' | 'email' | 'manual'

export type DomainClaim = {
  claim_id: string
  domain: string
  method: ClaimMethod
  strength: string
  state: string
  instruction: string
  evidence?: string | null
}

async function request(
  path: string,
  init?: { method: 'POST' | 'PUT'; body?: unknown },
): Promise<unknown> {
  const headers: Record<string, string> = {}
  if (init?.body !== undefined) headers['Content-Type'] = 'application/json'

  const token = csrfToken()
  if (token) headers['X-CSRF-Token'] = token

  const response = await fetch(path, {
    method: init?.method ?? 'GET',
    headers,
    body: init?.body === undefined ? undefined : JSON.stringify(init.body),
    credentials: 'same-origin',
    cache: 'no-store',
  })

  if (response.status === 204) return null

  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    throw new AuthError(messageFrom(payload, 'That did not work.'), response.status)
  }
  return payload
}

export async function fetchCompany(): Promise<CurrentCompany> {
  return (await request('/api/companies/current')) as CurrentCompany
}

export async function startDomainClaim(domain: string, method: ClaimMethod): Promise<DomainClaim> {
  return (await request('/api/domains', {
    method: 'POST',
    body: { domain, method },
  })) as DomainClaim
}

export async function checkDomainClaim(claimId: string): Promise<DomainClaim> {
  return (await request(`/api/domains/${encodeURIComponent(claimId)}/check`, {
    method: 'POST',
  })) as DomainClaim
}

/**
 * The reporting assumptions, and what moving each one costs.
 *
 * `doc/13` §13, ADR 0025. `moves_tiles` is computed by the API against the
 * departments this company runs — never in the browser, and never written
 * down. A count of affected tiles is a claim, and the browser is the last place
 * that should be deciding one.
 */
export type ReportingSetting = {
  key: string
  label: string
  /** What it changes, in the question bank's voice. */
  changes: string
  /** How many of this company's tiles are computed differently if it moves. */
  moves_tiles: number
  moves_departments: string[]
  /** Whether changing it restates figures somebody may already have acted on. */
  restates: boolean
}

export type Reporting = {
  /** The currency every figure in the product is labelled in. Asked for
   *  nowhere before this panel, so every workspace assumed Omani rials. */
  currency: string
  country: string
  fiscal_year_start_month: number
  week_start: string
  timezone: string
  scale: string
  decimals: number
  /** `null` means never changed since registration. */
  changed_at: string | null
  settings: ReportingSetting[]
  may_administer: boolean
}

export type ReportingUpdate = {
  currency: string
  country: string
  fiscal_year_start_month: number
  week_start: string
  timezone: string
  scale: string
  decimals: number
}

export async function fetchReporting(): Promise<Reporting> {
  return (await request('/api/companies/current/reporting')) as Reporting
}

export async function saveReporting(update: ReportingUpdate): Promise<Reporting> {
  return (await request('/api/companies/current/reporting', {
    method: 'PUT',
    body: update,
  })) as Reporting
}

/** One department, and what turning it on would bring. */
export type DepartmentState = {
  value: string
  label: string
  running: boolean
  /** Derived by the API from the capability registry, never counted here. */
  capabilities: number
  answered: number
  unanswered: number
}

export type Departments = {
  departments: DepartmentState[]
  may_administer: boolean
}

export async function fetchDepartments(): Promise<Departments> {
  return (await request('/api/companies/current/departments')) as Departments
}

export async function saveDepartments(values: string[]): Promise<Departments> {
  return (await request('/api/companies/current/departments', {
    method: 'PUT',
    body: { departments: values },
  })) as Departments
}

/** One row of the workspace's trail. */
export type AuditEntry = {
  action: string
  actor_user_id: string | null
  target_type: string | null
  target_id: string | null
  reason: string | null
  at: string
}

export async function fetchAuditLog(): Promise<{ entries: AuditEntry[] }> {
  return (await request('/api/audit-log')) as { entries: AuditEntry[] }
}

/**
 * Presentation preferences — panel 2. Every field is a `persona.*` column and
 * **none of them authorises anything** (`doc/06` §2.6).
 */
export type Preferences = {
  language: string
  timezone: string
  communication_style: string | null
  default_landing_screen: string | null
  /** Inferred by the persona interview from what the founder said would go
   *  wrong. Shown, not editable — a checkbox list would turn a considered
   *  answer into a shopping basket. */
  priority_topics: string[]
}

export async function fetchPreferences(): Promise<Preferences> {
  return (await request('/api/auth/preferences')) as Preferences
}

export async function savePreferences(
  next: Omit<Preferences, 'priority_topics'>,
): Promise<Preferences> {
  return (await request('/api/auth/preferences', {
    method: 'PUT',
    body: next,
  })) as Preferences
}

/** One question in a department's block — panel 3. */
export type BlockQuestion = {
  key: string
  prompt: string
  /** Why it is asked. Every question carries one, and it is the sentence that
   *  makes answering feel worth it. */
  why: string
  answer_type: string
  /** The capability that reads the answer. Q33: a question with no consumer is
   *  a form field. */
  consumed_by: string
  answered: boolean
  /** A Contributor's answer waits for a manager at the review gate (Q31/D22). */
  proposed: boolean
  answer: unknown
}

export type DepartmentBlock = {
  department: string
  /** Served rather than inferred: a UI deciding for itself would be guessing at
   *  an authority rule. */
  may_answer: boolean
  /** Whether this caller's answer becomes fact or waits as a proposal. */
  binds: boolean
  questions: BlockQuestion[]
}

export async function fetchBlock(department: string): Promise<DepartmentBlock> {
  return (await request(
    `/api/onboarding/departments/${encodeURIComponent(department)}/block`,
  )) as DepartmentBlock
}

export async function answerBlock(
  department: string,
  answers: Array<{ key: string; value: unknown }>,
): Promise<DepartmentBlock> {
  return (await request(
    `/api/onboarding/departments/${encodeURIComponent(department)}/block`,
    { method: 'POST', body: { answers } },
  )) as DepartmentBlock
}

/** The Company Brain — panel 10, read-only. */
export type Brain = {
  version: number
  generated_by: string
  unavailable_reason: string
  profile: string | null
  products_services: string | null
  target_customers: string | null
  goals: string | null
  /** What it had to assume. Part of the response rather than an internal
   *  detail: a brain the founder cannot audit is one they must take on trust. */
  assumptions: string[]
  provenance: string[]
}

export async function fetchBrain(): Promise<Brain> {
  return (await request('/api/onboarding/brain')) as Brain
}

/** One entity this login holds — ADR 0026. */
export type WorkspaceChoice = {
  workspace_id: string
  name: string
  role: string
  active: boolean
}

export async function fetchWorkspaces(): Promise<{ workspaces: WorkspaceChoice[] }> {
  return (await request('/api/auth/workspaces')) as { workspaces: WorkspaceChoice[] }
}

/**
 * Move the session to another entity.
 *
 * **The caller must reload the page afterwards rather than update state.** Every
 * figure, every department list and every cached fetch in the browser belongs to
 * the entity that was active when it was read, and entity A's numbers under
 * entity B's name is the worst failure this product can have — it looks entirely
 * normal on screen. `switchWorkspace` therefore returns nothing useful: there is
 * nothing safe to do with a response except leave.
 */
export async function switchWorkspace(workspaceId: string): Promise<void> {
  await request('/api/auth/workspace', {
    method: 'POST',
    body: { workspace_id: workspaceId },
  })
}
