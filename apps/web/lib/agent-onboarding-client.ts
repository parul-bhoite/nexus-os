import { messageFrom } from '@/lib/api-error'
import { csrfToken } from '@/lib/auth-client'

/**
 * Browser-side calls for the guided onboarding.
 *
 * Like every other client here these go to this app's own `/api/*` routes
 * rather than to the API directly — the session cookie is `httponly` and
 * `SameSite=Lax`, and both only hold while the request is first-party.
 *
 * **Nothing in this file decides anything.** In particular it never sends the
 * field an answer belongs to: `submitAnswer` posts text and nothing else, and
 * the server reads the target off the agent's own last turn. A client that
 * could name the target could choose the sensitivity its answer is stored at,
 * which is exactly what the field catalogue exists to take out of its hands.
 */

export type Turn = {
  role: 'agent' | 'user'
  text: string
  /** The declared field this turn is bound to, if any. Display only. */
  target: string | null
  /** L1–L5, from the field catalogue. Shown so a person can see where an answer lands. */
  scope: number | null
}

/**
 * Who is reading, as they described themselves at sign-up.
 *
 * Every field is optional because every column behind it is nullable — an
 * invited user may have typed no job title, and a workspace may have no name
 * the person recognises. The greeting says the parts that exist and nothing
 * about the parts that do not.
 *
 * **`designation` is not `role`.** This is what the user *said* they do;
 * `membership.role` is what they are *allowed* to do, and it is deliberately
 * not on this wire. Rendering authorisation in a greeting is how it starts
 * being treated as conversational.
 */
export type Viewer = {
  name?: string | null
  designation?: string | null
  department?: string | null
  company?: string | null
}

export type BriefStatement = {
  field: string
  text: string
  confidence: 'read' | 'inferred'
  source?: string
}

export type Brief = {
  statements?: BriefStatement[]
  needs_you?: { topic: string; why_only_you: string }[]
  assumptions?: { text: string; evidence: string }[]
  opening_line?: string
}

export type AgentState = {
  active: boolean
  /** Already finished. Distinct from `active: false`, which also means "never started". */
  completed: boolean
  phase: 'analysing' | 'brief' | 'discovery' | 'persona' | 'assembling' | 'ready'
  domain: string | null
  turns: Turn[]
  brief: Brief
  persona: { fields?: { key: string; label: string; value: string; derived_from: string }[] }
  context: {
    preamble?: string
    facts?: { key: string; value: string; scope: number }[]
    known_gaps?: { topic: string; unlocked_by: string }[]
  }
  answered: number
  ceiling: number
  /** URLs the fetcher retrieved. Shown while the read runs. */
  pages_read: string[]
  /**
   * Optional on this type, always sent by the server. Optional because a
   * response cached from before the field existed is a blank greeting, not a
   * crash — and because the greeting is decoration on a screen whose job is the
   * interview.
   */
  viewer?: Viewer
}

export type NextQuestion = {
  done: boolean
  question: string | null
  target: string | null
  scope: number | null
  choices: string[]
  reason: string | null
}

/**
 * Raised when the API says onboarding needs a model and none is configured.
 *
 * Kept distinct from a generic failure because the remedy is different and the
 * user can do nothing about it — the screen says so plainly rather than
 * offering a Retry that cannot work (ADR 0022).
 */
export class ModelUnavailableError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'ModelUnavailableError'
  }
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {}
  if (init.body !== undefined) headers['Content-Type'] = 'application/json'
  const token = csrfToken()
  if (token) headers['X-CSRF-Token'] = token

  const response = await fetch(path, { ...init, headers, credentials: 'same-origin' })
  if (response.ok) return (await response.json()) as T

  const payload = await response.json().catch(() => null)
  const detail = payload?.detail
  if (response.status === 503 && detail?.error === 'language_model_unavailable') {
    throw new ModelUnavailableError(detail.message ?? 'The assistant is not configured.')
  }
  throw new Error(messageFrom(payload, `The request failed (${response.status}).`))
}

export function readState(): Promise<AgentState> {
  return call<AgentState>('/api/onboarding/agent/state')
}

/**
 * Begin the journey. Takes nothing.
 *
 * The company being researched is the one on the workspace, read server-side.
 * The browser deliberately cannot name it — a client that could would be able
 * to point the crawl at another company and have the result written into its
 * own Brain, cited and sourced.
 */
/** Read the fetched pages and write the brief. The slow half, ~17s. */
export function read(): Promise<AgentState> {
  return call<AgentState>('/api/onboarding/agent/read', { method: 'POST' })
}

export function start(): Promise<AgentState> {
  return call<AgentState>('/api/onboarding/agent/start', { method: 'POST' })
}

export function confirmBrief(corrections: Record<string, string>): Promise<AgentState> {
  return call<AgentState>('/api/onboarding/agent/brief', {
    method: 'POST',
    body: JSON.stringify({ corrections }),
  })
}

export function openDiscovery(answer: string): Promise<AgentState> {
  return call<AgentState>('/api/onboarding/agent/discovery', {
    method: 'POST',
    body: JSON.stringify({ answer }),
  })
}

export function nextQuestion(): Promise<NextQuestion> {
  return call<NextQuestion>('/api/onboarding/agent/next')
}

/** Text only. The field it answers is decided server-side — see the note above. */
export function submitAnswer(text: string): Promise<AgentState> {
  return call<AgentState>('/api/onboarding/agent/answer', {
    method: 'POST',
    body: JSON.stringify({ text }),
  })
}

/**
 * Advance the assembly by **one** stage, and return the state it reached.
 *
 * Not one call. The server runs persona, then Brain, then context — one per
 * request, committing each — so this is called until `phase` is `'ready'`.
 * `ASSEMBLY_LABEL` names what each call is doing; `assemblyDone` is the stop
 * condition, so the loop's terminating check lives next to the labels rather
 * than being spelled out at the call site.
 *
 * Which stage runs is the server's decision, read from the phase on the
 * session row. This function deliberately sends nothing: a client that could
 * name the stage could skip one.
 */
export function finish(): Promise<AgentState> {
  return call<AgentState>('/api/onboarding/agent/finish', { method: 'POST' })
}

/** What the next `finish()` call will be doing, keyed by the phase it starts from. */
export const ASSEMBLY_LABEL: Record<string, string> = {
  discovery: 'Building your Persona…',
  persona: 'Building your Company Brain…',
  assembling: 'Personalising your workspace…',
}

export function assemblyDone(state: AgentState): boolean {
  return state.phase === 'ready' || state.completed
}

export const SCOPE_LABEL: Record<number, string> = {
  1: 'L1 Company public',
  2: 'L2 Company internal',
  3: 'L3 Department',
  4: 'L4 Restricted',
  5: 'L5 Personal',
}
