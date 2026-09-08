import { messageFrom } from '@/lib/api-error'

/**
 * Browser-side auth calls.
 *
 * All of these go to this app's own `/api/auth/*` routes, never to the API
 * directly — see `lib/auth-proxy.ts` for why that matters to the cookie flags.
 */

/** Mirrors the API's `MIN_PASSWORD_LENGTH`. Checked there too; this is only so the form can say so first. */
export const MIN_PASSWORD_LENGTH = 12

export type WorkspaceSummary = {
  workspace_id: string
  name: string
  role: string
}

export type SessionState = {
  user_id: string
  /** The address this account signs in with. Optional so a client built against
   *  an older API renders the id rather than the string "undefined". */
  email?: string
  workspaces: WorkspaceSummary[]
  active_workspace_id: string | null
}

/**
 * The CSRF token the API set in a readable cookie at login.
 *
 * Readable on purpose: state-changing requests must echo it in a header, and
 * that is exactly what an attacker on another origin cannot do — they can make
 * the browser *send* the cookie but never read it.
 */
export function csrfToken(): string | null {
  if (typeof document === 'undefined') return null
  for (const part of document.cookie.split(';')) {
    const [name, ...rest] = part.trim().split('=')
    if (name === 'nexus_csrf') return decodeURIComponent(rest.join('='))
  }
  return null
}

/**
 * Whether a session *looks* present, for choosing what to render first.
 *
 * A hint, never a decision. The cookie is client-visible and therefore
 * client-forgeable; every real answer comes from the API. Using this to gate
 * access rather than to pick an initial view would be the mistake.
 *
 * **Never call this during render.** `document.cookie` is empty on the server
 * and populated on the client, so the two renders pick different branches and
 * React tears the subtree down — finding F5, which cost `/invitations/accept`
 * its server rendering on every single load. `useLooksSignedIn` in
 * `lib/hooks.ts` is the safe way to read it.
 */
export function looksSignedIn(): boolean {
  return csrfToken() !== null
}



export class AuthError extends Error {
  readonly status: number
  /**
   * The API's `detail`, unflattened.
   *
   * `messageFrom` turns whatever arrived into a string for display, which is
   * right for the common case and lossy for the uncommon one: a 409 from
   * `/companies` carries an *object* naming the workspace whose domain is
   * already registered, and that id is what lets the UI offer a join request
   * instead of asking the user to retype a domain that was correct.
   */
  readonly detail: unknown
  constructor(message: string, status: number, detail?: unknown) {
    super(message)
    this.status = status
    this.detail = detail
  }
}

async function post(path: string, body?: unknown): Promise<unknown> {
  const headers: Record<string, string> = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'

  const token = csrfToken()
  if (token) headers['X-CSRF-Token'] = token

  const response = await fetch(path, {
    method: 'POST',
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    // Same origin, so cookies ride along; stated rather than assumed.
    credentials: 'same-origin',
    cache: 'no-store',
  })

  if (response.status === 204) return null

  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    throw new AuthError(
      messageFrom(payload, 'Something went wrong.'),
      response.status,
      (payload as { detail?: unknown } | null)?.detail,
    )
  }
  return payload
}

/**
 * Create the account.
 *
 * `displayName` is what the agent calls the person for the rest of onboarding,
 * so it is asked for here rather than derived from the email local part —
 * "founder" is not a name, and greeting somebody by their inbox is worse than
 * not greeting them.
 */
export async function register(
  email: string,
  password: string,
  { displayName, phone }: { displayName?: string; phone?: string } = {},
): Promise<void> {
  await post('/api/auth/register', {
    email,
    password,
    display_name: displayName?.trim() || null,
    phone: phone?.trim() || null,
  })
}

export async function login(email: string, password: string): Promise<SessionState> {
  return (await post('/api/auth/login', { email, password })) as SessionState
}

export async function logout(): Promise<void> {
  await post('/api/auth/logout')
}

/** Spend a verification token. Throws `AuthError` if it is expired or used. */
export async function verifyEmail(token: string): Promise<void> {
  await post('/api/auth/verify-email', { token })
}

/**
 * Ask for a password-reset link.
 *
 * Returns nothing, and cannot fail differently for a known and an unknown
 * address — the API answers identically on purpose. Any caller that branches on
 * the result to say "we found you" reintroduces the oracle the endpoint exists
 * to close, so there is nothing here to branch on.
 */
export async function requestPasswordReset(email: string): Promise<void> {
  await post('/api/auth/password-reset/request', { email })
}

/** Spend a reset token and set a new password. Signs the account out everywhere. */
export async function confirmPasswordReset(token: string, password: string): Promise<void> {
  await post('/api/auth/password-reset/confirm', { token, password })
}

/** The current session, or `null` when there is none. */
export async function fetchSession(): Promise<SessionState | null> {
  const response = await fetch('/api/auth/session', {
    credentials: 'same-origin',
    cache: 'no-store',
  })
  if (response.status === 401) return null
  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    throw new AuthError(messageFrom(payload, 'Could not load your account.'), response.status)
  }
  return payload as SessionState
}


// ── Company registration (P5) ─────────────────────────────────

export type CompanyDetails = {
  name: string
  website_url: string
  /**
   * What the person says they do. Presentation only — it shapes what the agent
   * asks and what the dashboard leads with. Access comes from the membership
   * role, which this form cannot set.
   */
  designation?: string | null
  department?: string | null
}

/**
 * One option for the Department field, as the server names it.
 *
 * `label` is served rather than derived. Title-casing `value` in the browser
 * renders "Hr" for the department the rest of the product calls "People", which
 * is finding F13 — three spellings for one thing, because three surfaces each
 * capitalised the enum themselves.
 */
export type DepartmentChoice = {
  value: string
  label: string
}

/**
 * The seven departments, for a form that runs before any workspace exists.
 *
 * Not `CurrentScope`-guarded and not cached here: it is one small request on a
 * page the user spends a while filling in, and a stale copy in a module-level
 * variable would outlive a deploy that changed the list.
 */
export async function fetchDepartments(): Promise<DepartmentChoice[]> {
  const response = await fetch('/api/departments', {
    credentials: 'same-origin',
    cache: 'no-store',
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new AuthError(messageFrom(payload, 'Could not load the department list.'), response.status)
  }
  return (await response.json()) as DepartmentChoice[]
}

export type RegisteredCompany = {
  workspace_id: string
  domain: string
  domain_verified: boolean
}

/**
 * The shape a 409 carries when the domain is already held by a verified
 * company. It is an *offer*, not only a refusal — the caller can turn it into a
 * join request without asking the user to retype anything.
 */
export type JoinOffer = {
  detail: string
  workspace_id: string
  join_request_path: string
}

export class DomainTakenError extends AuthError {
  readonly offer: JoinOffer
  constructor(offer: JoinOffer) {
    super(offer.detail, 409)
    this.offer = offer
  }
}

export async function registerCompany(
  details: CompanyDetails,
  { confirmSeparateCompany = false }: { confirmSeparateCompany?: boolean } = {},
): Promise<RegisteredCompany> {
  try {
    return (await post('/api/companies', {
      ...details,
      confirm_separate_company: confirmSeparateCompany,
    })) as RegisteredCompany
  } catch (error) {
    // A 409 whose detail is an object is the join offer. FastAPI puts a dict
    // detail through unchanged, and `messageFrom` would flatten it to a string
    // — losing the workspace id the offer exists to carry.
    if (error instanceof AuthError && error.status === 409) {
      const offer = error.detail
      if (offer && typeof offer === 'object' && 'join_request_path' in offer) {
        throw new DomainTakenError(offer as JoinOffer)
      }
    }
    throw error
  }
}

export async function requestToJoin(websiteUrl: string, message?: string): Promise<void> {
  await post('/api/join-requests', { website_url: websiteUrl, message: message ?? null })
}
