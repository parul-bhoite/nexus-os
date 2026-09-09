import { messageFrom } from '@/lib/api-error'
import { AuthError } from '@/lib/auth-client'

/**
 * The seven director pages.
 *
 * Every field here is read from the API and rendered. Nothing is computed in the
 * browser, and there is deliberately no place to put a value: an `Offering` has
 * a name, what it will show, its state and its unlock — and no number. The
 * figures arrive in a later milestone from `calculators/`, which is pure.
 */

/**
 * Doc 05 §0's states, plus `planned`.
 *
 * `locked` means "connect something and this works". `planned` means the widget
 * does not exist yet. Collapsing them would turn a placeholder into a promise,
 * so the two are distinct all the way from `app/domain/dashboards.py` to here.
 */
export type WidgetState =
  | 'live'
  | 'partial'
  | 'locked'
  | 'warming'
  | 'self_reported'
  | 'stale'
  | 'unavailable'
  | 'planned'

/**
 * The nine block kinds (`doc/13` §6). The section is the unit of navigation,
 * the block is the unit of rendering, and the capability is the unit of truth.
 *
 * `studio` is the ninth, found while assigning all eighty capabilities: a
 * generator takes an instruction and produces an artefact, and forcing the
 * content studio and the proposal studio into `panel` would have made a third
 * of the product render as an explanation of itself.
 */
export type BlockKind =
  | 'metric'
  | 'trend'
  | 'table'
  | 'board'
  | 'cards'
  | 'queue'
  | 'facts'
  | 'panel'
  | 'studio'

/** One capability, as the rail renders it. */
export type DirectorBlock = {
  /** The canonical capability id — `finance.runway_alert`. */
  key: string
  /** Doc 05's numbering, or empty for a capability the wider document never had. */
  doc05_id: string
  name: string
  shows: string
  block: BlockKind
  state: WidgetState
  /** What this needs, in words. Empty only when nothing is missing. */
  unlock: string
  needs: string[]
}

/** One tab on the rail. */
export type Section = {
  key: string
  /** Doc 08's own wording, served rather than derived (finding F13). */
  label: string
  blocks: DirectorBlock[]
  /**
   * How many of this tab's blocks are not `planned`.
   *
   * The page opens on the first tab where this is non-zero. On a day-one
   * dashboard that is Setup — and always opening on Overview would greet a new
   * customer with five tiles that all say "not built yet" while the one tab
   * with content sits two along.
   */
  available?: number
}

/** One answer, read back with everything needed to check it. */
export type SetupFact = {
  key: string
  question: string
  answer: string
  answered_at: string
  /** The capability that consumes it. An answer whose consumer cannot be named
   *  is a form field (Q33), and this is where that shows. */
  reads_it: string
}

/** One stated risk, and what would confirm or refute it. */
export type WatchItem = {
  key: string
  label: string
  stated: string
  answered_at: string
  measured_by: string
  needs: string
}

/**
 * The Setup and Watchlist tabs' content.
 *
 * Fetched separately from the rail: finding #23 is that the dashboard already
 * spends 25 to 30 round trips, and most visits to a director page never open
 * Setup.
 */
export type DirectorSetup = {
  department: string
  facts: SetupFact[]
  watch: WatchItem[]
}

/** A figure NEXUS refuses to ask for, and where it comes from instead. */
export type NotAsked = {
  what: string
  source: string
}

/**
 * The reserved assistant panel (Q67).
 *
 * `available` is false everywhere today. A blank region where a feature is
 * coming reads as a bug and a fake one reads as a lie, so the panel names the
 * director and the questions it will answer.
 */
export type Assistant = {
  director: string
  questions: string[]
  available: boolean
}

export type Offering = {
  /** Doc 05's own numbering — `3.4` is the Growth Plan. What the tile shows as
   * its traceability label, because it points at the paragraph that specified it. */
  id: string
  /** The canonical capability id — `marketing.growth_planner`. The join to the
   * question bank, the tool ledger and the skill that will narrate it. Not
   * displayed today; carried so a client never has to guess it from `id`. */
  key: string
  name: string
  shows: string
  state: WidgetState
  /** What this needs, in words. Empty only when nothing is missing. */
  unlock: string
  needs: string[]
  phase: number
  note: string
}

export type DirectorSummary = {
  department: string
  /** The department's name for a person. Optional so a client built against an
   *  older API falls back rather than rendering "undefined" in the nav. */
  label?: string
  title: string
  remit: string
  scoreable: boolean
  path: string
  offering_count: number
  /**
   * Q27. How many of this department's questions are still unanswered.
   *
   * Optional because a client built against an older API gets `undefined`
   * rather than a wrong zero — and zero would read as "nothing to do", which is
   * the one thing it must not say when the truth is unknown.
   */
  unanswered_questions?: number
}

export type Dashboards = {
  directors: DirectorSummary[]
  /** Where to send this person. `null` when they hold no department. */
  shell?: {
    score: number | null
    score_denominator: number
    capabilities_delivered: number
    capabilities_total: number
    assistant_reserved: boolean
  }
  /** Optional so a client built against an older API gets `undefined` rather
   *  than a wrong zero — the same reason `unanswered_questions` is optional. */

  landing: string | null
  delivered_count: number
}

export type Director = {
  department: string
  title: string
  remit: string
  scoreable: boolean
  path: string
  /** The flat catalogue. Optional so an older API does not break this client,
   *  and going once nothing reads it. */
  offerings?: Offering[]
  /** The rail. Only tabs with something on them — doc 08 draws five that no
   *  capability fills yet, and a tab somebody clicks into to find nothing is
   *  worse than a tab that is not there. */
  sections?: Section[]
  /** Capabilities in this director's remit that doc 08's cut has no section
   *  for (§11's deliberate gaps). Neither locked nor coming. */
  catalogue?: DirectorBlock[]
  /** Doc 08 §2B to §8B — what NEXUS will not ask you for, and what it reads
   *  instead. A product surface rather than an internal rule. */
  not_asked?: NotAsked[]
  assistant?: Assistant
}

async function get(path: string): Promise<unknown> {
  const response = await fetch(path, { credentials: 'same-origin', cache: 'no-store' })
  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    throw new AuthError(messageFrom(payload, 'Could not load that dashboard.'), response.status)
  }
  return payload
}

export async function fetchDashboards(): Promise<Dashboards> {
  return (await get('/api/dashboards')) as Dashboards
}

export async function fetchSetup(department: string): Promise<DirectorSetup> {
  return (await get(
    `/api/dashboards/${encodeURIComponent(department)}/setup`,
  )) as DirectorSetup
}

export async function fetchDirector(department: string): Promise<Director> {
  return (await get(`/api/dashboards/${encodeURIComponent(department)}`)) as Director
}

export const STATE_LABEL: Record<WidgetState, string> = {
  live: 'Live',
  partial: 'Partial',
  locked: 'Locked',
  warming: 'Warming',
  self_reported: 'Entered by you',
  stale: 'Out of date',
  unavailable: 'Could not compute',
  planned: 'Not built yet',
}
