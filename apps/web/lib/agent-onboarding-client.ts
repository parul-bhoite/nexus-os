import { messageFrom } from '@/lib/api-error'
import { AuthError, csrfToken } from '@/lib/auth-client'

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
  /** The catalogue key. What a correction is keyed by — never shown. */
  field: string
  /**
   * The field's human name, resolved from the catalogue server-side.
   *
   * Optional only so a response cached from before it existed renders the key
   * rather than `undefined`. The screen used to show `field` directly, which
   * put `brain.products_services` above a paragraph somebody was being asked
   * to correct.
   */
  label?: string
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
  /**
   * Where the journey is. `documents` and `tools` sit between the interview and
   * the assembly, and that position is the whole feature: the Persona and the
   * Company Brain are built from whatever is in hand when `finish` runs, so
   * everything the person supplies has to be in hand first. The server refuses
   * `finish` from either of them, which is why this union is not merely a set
   * of screens.
   */
  phase:
    | 'analysing'
    | 'brief'
    | 'discovery'
    | 'documents'
    | 'tools'
    | 'persona'
    | 'assembling'
    | 'ready'
  domain: string | null
  turns: Turn[]
  brief: Brief
  /**
   * The persona draft, as the builder wrote it.
   *
   * `summary` is one sentence over the fields and has always been on this wire
   * — `persona_draft` is returned verbatim and `persona-builder` has it as a
   * required output. It went unread while the persona was a list of rows on a
   * panel; it is the headline of the confirmation step now, because "does this
   * sound like you" is a question about a sentence and not about a table.
   */
  persona: {
    fields?: { key: string; label: string; value: string; derived_from: string }[]
    summary?: string
  }
  context: {
    preamble?: string
    facts?: { key: string; value: string; scope: number }[]
    known_gaps?: { topic: string; unlocked_by: string }[]
  }
  answered: number
  ceiling: number
  /**
   * How many assembly stages have committed. Monotone.
   *
   * The Brain is built in groups and every group leaves the phase at `persona`,
   * so a loop watching only the phase sees "nothing moved" after the first one
   * and stops with a half-built Brain. This is what makes "the phase did not
   * change *and* neither did this" a real stall rather than a false one.
   *
   * Optional so a response predating it reads as 0 rather than `undefined`.
   */
  assembly_step?: number
  /** URLs the fetcher retrieved. Shown while the read runs. */
  pages_read: string[]
  /**
   * The crawl ran and the site gave us nothing.
   *
   * Not the same as `pages_read` being empty, which is also true *before* the
   * crawl. The screen has to tell "still fetching" from "there is nothing to
   * fetch and it is your turn", because only the second one may replace the
   * reading bubble with three questions.
   *
   * Optional so a response cached from before the field existed reads as false
   * rather than undefined.
   */
  site_unreadable?: boolean
  /**
   * Optional on this type, always sent by the server. Optional because a
   * response cached from before the field existed is a blank greeting, not a
   * crash — and because the greeting is decoration on a screen whose job is the
   * interview.
   */
  viewer?: Viewer
}

/**
 * What `/answer` and `/discovery` now return: the state, and the question that
 * follows, in one round trip.
 *
 * These used to be two sequential requests — post the answer, then `GET /next`
 * — and the second repeated everything the first had already done: open a
 * transaction, set the scoping GUC, load the session and every turn in it, read
 * the same user row. Against a database ~340ms away that was over two seconds
 * per question spent arriving back where the first request already was.
 *
 * **`question` may be null, and that is not an error.** The server records the
 * answer and generates the question in one transaction, so a failure in
 * generation must not be allowed to roll the answer back. When it fails the
 * answer stays saved, this comes back null, and the caller asks `nextQuestion()`
 * — which is why that endpoint still exists.
 */
export type AnswerTurn = {
  state: AgentState
  question: NextQuestion | null
}

export type Tool = {
  id: string
  name: string
  department: string
  department_label: string
  /** What connecting it turns on. A capability, never a finding. */
  unlocks: string
  /** `crm` for the four that are alternatives to each other, `tool` otherwise. */
  kind: string
  declared: boolean
  /**
   * Whether a connect flow exists for this tool **today**. False for all nine.
   *
   * From the server rather than assumed here, so the day one becomes true the
   * screen stops saying "we will ask you to connect this" without a second list
   * in TypeScript to remember to edit.
   */
  connectable: boolean
}

export type ToolCatalogue = {
  /** The catalogue, this company's own departments first. Nothing is removed. */
  tools: Tool[]
  declared: string[]
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
  // `AuthError` rather than a bare `Error`, matching `dashboard-client`. It
  // carries the status, and the status is the only thing that distinguishes an
  // expired session from a server fault — a distinction the caller has to make,
  // because one is fixed by signing in and the other by trying again.
  //
  // This journey runs for minutes across a dozen requests, so a session
  // expiring *mid-interview* is an ordinary event here rather than an edge
  // case, and it used to surface as "The request failed (401)." in a red box
  // with nothing to click.
  throw new AuthError(
    messageFrom(payload, `The request failed (${response.status}).`),
    response.status,
    detail,
  )
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

export function openDiscovery(answer: string): Promise<AnswerTurn> {
  return call<AnswerTurn>('/api/onboarding/agent/discovery', {
    method: 'POST',
    body: JSON.stringify({ answer }),
  })
}

/**
 * Supply the brief by hand, when the site could not be read.
 *
 * Goes straight into the interview: there is no brief-confirmation step on this
 * path, because that step exists to correct what a machine claimed and there is
 * nothing to correct in three sentences you just typed.
 */
export function describeCompany(fields: {
  profile: string
  target_customers: string
  goals: string
}): Promise<AgentState> {
  return call<AgentState>('/api/onboarding/agent/describe', {
    method: 'POST',
    body: JSON.stringify(fields),
  })
}

/**
 * The tool catalogue for this company, and what it has already declared.
 *
 * Fetched rather than held here, because the ids are a closed set with a
 * `CHECK` constraint behind them and `connectable` is a fact about what the
 * server can actually do today. A hardcoded list in the browser would go on
 * offering nine tools after a tenth was added, and would go on saying "we will
 * ask you to connect this later" after the first connect flow shipped.
 */
export function readTools(): Promise<ToolCatalogue> {
  return call<ToolCatalogue>('/api/onboarding/agent/tools')
}

/**
 * Leave the documents step. Uploading is `uploadDocument` in `documents-client`.
 *
 * Two calls rather than one because they are two acts: the last upload of a
 * batch must not also close the step, or somebody who wanted to add a fourth
 * file finds it shut behind them. `skipped` is recorded, not obeyed — the step
 * is skippable either way.
 */
export function documentsDone(skipped: boolean): Promise<AgentState> {
  return call<AgentState>('/api/onboarding/agent/documents', {
    method: 'POST',
    body: JSON.stringify({ skipped }),
  })
}

/**
 * Declare which systems this company runs on. **The last step before assembly.**
 *
 * Sends ids only. No state and no credentials: every row this writes is
 * `declared`, because that is all the product can honestly claim until the
 * OAuth half lands. The phase deliberately stays at `tools` afterwards, so the
 * caller follows this with `finish()` — see `AgentOnboarding`.
 *
 * Replaces rather than adds, so returning to the step and unticking something
 * is believed.
 */
export function declareTools(providers: string[], skipped: boolean): Promise<AgentState> {
  return call<AgentState>('/api/onboarding/agent/tools', {
    method: 'POST',
    body: JSON.stringify({ providers, skipped }),
  })
}

export function nextQuestion(): Promise<NextQuestion> {
  return call<NextQuestion>('/api/onboarding/agent/next')
}

/** Text only. The field it answers is decided server-side — see the note above. */
export function submitAnswer(text: string): Promise<AnswerTurn> {
  return call<AnswerTurn>('/api/onboarding/agent/answer', {
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
  // `tools`, not `discovery`. The persona used to be built straight off the
  // interview; it is now built after the documents and the declared stack are
  // in, which is what makes both of them grounding rather than an afterthought.
  // `discovery` is kept only so that a session left mid-flight by an older
  // build still gets a sentence rather than "Building…".
  discovery: 'Building your Persona…',
  tools: 'Building your Persona…',
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
