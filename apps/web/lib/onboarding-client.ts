import { messageFrom } from '@/lib/api-error'
import { AuthError, csrfToken } from '@/lib/auth-client'

/**
 * Browser-side calls for workspace setup.
 *
 * Like the auth calls, these go to this app's own `/api/*` routes rather than
 * to the API directly — see `lib/auth-proxy.ts`. The session cookie is
 * `httponly` and `SameSite=Lax`, and both properties only hold while the
 * request is first-party.
 *
 * Nothing here decides anything. `writable`, `can_administer` and the scope on
 * each question are read from the API and used to choose what to *render*; the
 * API refuses the write regardless of what this file believes. A field this
 * code hides is a presentation choice, and never the boundary.
 */

export type Choice = { value: string; label: string }

export type Stage = 'pass_1' | 'pass_2' | 'post_invite'

export type AnswerType =
  | 'text'
  | 'long_text'
  | 'single_choice'
  | 'multi_choice'
  | 'ranked'
  | 'money'
  | 'url'
  | 'user_list'

export type Question = {
  key: string
  prompt: string
  stage: Stage
  answer_type: AnswerType
  /** `L1`…`L5`. Where this answer will be stored, shown to the person giving it. */
  scope: string
  department: string | null
  required: boolean
  why: string
  options: Choice[]
  free_entry: boolean
  writable: boolean
  value: unknown
}

export type Invitation = {
  invitation_id: string
  email: string
  role: string
  departments: string[]
  state: 'pending' | 'accepted' | 'revoked' | 'expired'
  expires_at: string
}

export type IssuedInvitation = Invitation & {
  /** Where to send the invited person.
   *
   *  **The invitation is emailed too.** This said delivery was not wired up and
   *  pointed at a `TeamStep` that no longer exists — true when written, stale
   *  since P3 built the mailer. Still handed back, because an owner who would
   *  rather paste the link into a chat should be able to: the link alone grants
   *  nothing, since accepting requires being signed in as the address it names. */
  accept_path: string
}

export type AcceptResult = {
  outcome: 'accepted' | 'already_a_member'
  workspace_id: string | null
  workspace_name: string | null
  role: string | null
}

async function call(path: string, init: RequestInit = {}): Promise<unknown> {
  const headers: Record<string, string> = {}
  if (init.body !== undefined) headers['Content-Type'] = 'application/json'

  const token = csrfToken()
  if (token) headers['X-CSRF-Token'] = token

  const response = await fetch(path, {
    ...init,
    headers,
    credentials: 'same-origin',
    cache: 'no-store',
  })

  if (response.status === 204) return null

  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    throw new AuthError(messageFrom(payload, 'Something went wrong.'), response.status)
  }
  return payload
}

export type DepartmentOption = {
  value: string
  /** How to name it on screen. Optional so a client built against an older API
   *  falls back to the key rather than rendering "undefined". */
  label?: string
  selected: boolean
}

export type SpineState = {
  stage: { current: string; completed: string[]; stages: string[]; finished: boolean }
  company_questions: {
    key: string
    prompt: string
    why: string
    required: boolean
    assumption_when_unsure: string | null
  }[]
  departments: DepartmentOption[]
  recommended: { min: number; max: number }
}

/** Where the founder is, what they have finished, and which departments they run. */
export async function fetchState(): Promise<SpineState> {
  return (await call('/api/onboarding/state')) as SpineState
}

export async function fetchInvitations(): Promise<Invitation[]> {
  const payload = (await call('/api/invitations')) as { invitations: Invitation[] }
  return payload.invitations
}

export async function createInvitation(input: {
  email: string
  role: string
  departments: string[]
}): Promise<IssuedInvitation> {
  return (await call('/api/invitations', {
    method: 'POST',
    body: JSON.stringify(input),
  })) as IssuedInvitation
}

export async function revokeInvitation(id: string): Promise<void> {
  await call(`/api/invitations/${id}/revoke`, { method: 'POST' })
}

export async function acceptInvitation(token: string): Promise<AcceptResult> {
  return (await call('/api/invitations/accept', {
    method: 'POST',
    body: JSON.stringify({ token }),
  })) as AcceptResult
}

/**
 * How to name a department when the API has not supplied a label.
 *
 * Finding F13: the same department read `hr` in the API, "Hr" wherever a client
 * title-cased the key, and "People" in the dashboard nav. The endpoints that
 * matter now serve a `label`, and this is the fallback for the one caller left
 * that carries only a key — `DirectorPage`. Kept in step with `LABELS` in
 * `app/domain/departments.py`, which is the source.
 */
const DEPARTMENT_LABELS: Record<string, string> = {
  marketing: 'Marketing',
  sales: 'Sales',
  finance: 'Finance',
  operations: 'Operations',
  hr: 'People',
  strategy: 'Strategy',
  executive: 'Chief of Staff',
}

export function departmentLabel(department: string): string {
  return DEPARTMENT_LABELS[department] ?? department
}
