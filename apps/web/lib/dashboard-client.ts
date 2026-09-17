import { messageFrom } from '@/lib/api-error'
import { AuthError, csrfToken } from '@/lib/auth-client'

/**
 * The seven director pages.
 *
 * Every field here is read from the API and rendered. **Nothing is computed in
 * the browser** — that rule has not changed and is the point of the whole
 * layering, but the sentence that used to follow it has: there is now a place
 * to put a value.
 *
 * `DirectorBlock.figure` carries a score, its denominator and the checks that
 * produced it, all from `calculators/audit.py` via `grounding/compute.py`. Even
 * the percentage is served rather than divided here, so two clients cannot
 * round differently from the drawer that shows the working. An `Offering` still
 * has no number: that is `doc/05`'s row, and only a block is a thing on a
 * screen.
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

/**
 * One observation and the points it contributed.
 *
 * `evidence` is the calculator's own words and is an *observation*, never
 * advice — "0 internal links", not "add internal links". Turning one into the
 * other in the browser would be giving guidance nobody computed.
 */
export type FigureCheck = {
  id: string
  label: string
  passed: boolean
  weight: number
  evidence: string
}

/**
 * A computed figure, its denominator, and its working.
 *
 * `label` and `measures` are not decoration and not the capability's name.
 * `marketing.brand_intelligence` is presented as "Brand Intelligence" and
 * promises voice consistency; `score_brand` measures whether a first-time
 * visitor can tell what the company does. Both are true and only one is what
 * the number says, so `measures` is rendered next to it — the guard against a
 * correctly-computed figure sitting under a headline that misdescribes it.
 */
export type ScoreFigure = {
  /** The tag. Narrowed on exhaustively (ADR 0033), so a third kind fails to
   *  compile at every consumer rather than falling silently through a branch. */
  kind: 'score'
  label: string
  /** What was counted, and what was not. Rendered, not stored for later. */
  measures: string
  score: number
  max_score: number
  percentage: number
  checks: FigureCheck[]
  checks_passed: number
  /** The page. A score whose page cannot be opened is unverifiable. */
  source_url: string
  /** When the page was fetched. Stands in for the `stale` state, which the
   *  route deliberately does not reach because nothing re-crawls on a
   *  schedule. */
  measured_at: string
  method: string
}

/**
 * A counted, totalled figure — ADR 0033's second kind.
 *
 * **There is no denominator and none is invented.** A pipeline is not a fraction
 * of anything; a target to divide by would be a number the customer never gave
 * us, which is I1's prohibition arriving as a helpful-looking percentage.
 */
export type AmountFigure = {
  kind: 'amount'
  label: string
  /** What was counted **and what was not** — the same guard the scored figure
   *  carries, against a correct number under a headline promising more. */
  measures: string
  /** The population the total came from. Not something to divide by. */
  count: number
  /**
   * Minor units against `currency`. **`null` is not zero**: it means nothing
   * could be totalled — no priced items, or more than one currency, and adding
   * those needs a rate whose source and date nobody can see. Zero would say the
   * pipeline is worth nothing (I10).
   */
  total_minor: number | null
  /** The provider's own, never assumed to be the reporting currency. `null`
   *  exactly when `total_minor` is. */
  currency: string | null
  /** Items in `count` the total leaves out. Part of the figure: a total that
   *  did not say what it omitted is a total presented as complete. */
  uncounted: number
  /** What `uncounted` means here, in the calculator's words. */
  uncounted_label: string
  /** Where it was read from — a provider, because a CRM record has no page to
   *  open. The scored figure's `source_url` is its equivalent. */
  source: string
  measured_at: string
  method: string
}

/** One tile carries one kind. The union cannot express both or neither. */
export type Figure = ScoreFigure | AmountFigure

/**
 * A stored sentence about a figure, and enough to trace it.
 *
 * `prompt_version` names the `SKILL.md` that wrote it, and is shown in the
 * working drawer beside the calculator's `method` — so a disputed sentence
 * traces back to its instructions as readily as a disputed number traces back
 * to its arithmetic.
 */
export type Narration = {
  prose: string
  narrated_at: string
  prompt_version: string
}

/**
 * Why there is no sentence, named rather than described.
 *
 * Mirrors `UnavailableReason` on the API. The strings matter to this client for
 * exactly one decision — whether to offer the button again — and never for
 * composing copy: the wording is always the server's `message`.
 */
export type NarrationReason =
  | 'missing_input'
  | 'model_unavailable'
  | 'skill_disabled'
  | 'budget_exhausted'
  | 'provider_failed'
  | 'schema_invalid'
  | 'invented_number'
  | 'refused'

/**
 * What one attempt did — which is a different question from what a tile holds.
 *
 * The GET says what is true now; this says what just happened. That is why no
 * refusal reason is stored on `DirectorBlock`: a reason kept there would
 * resurrect yesterday's "your allowance is spent" on every page load, hours
 * after the allowance reset.
 */
export type NarrationResult = {
  key: string
  outcome: 'answered' | 'unavailable'
  /** Empty unless `outcome` is `unavailable`. */
  reason: string
  /**
   * Never empty, and always the server's words.
   *
   * A reason-to-sentence map in the browser is the failure `unlock` already
   * avoids: one wording change would then have to be made in as many places as
   * there are clients, and a screen could ship with the space drawn and the
   * copy forgotten.
   */
  message: string
  narration?: Narration | null
  /** Empty when no row was written, which happens only when nothing ran. */
  generation_id: string
  /**
   * The figure the sentence describes.
   *
   * Compared against the one on screen: if the page was re-crawled between load
   * and click, the sentence explains a number the reader cannot see, and saying
   * so is better than showing it.
   */
  measured_at: string
  tokens_left_today: number
}

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
  /**
   * The computed number, when there is one.
   *
   * Absent for every capability nothing computes, which is still most of them,
   * and **never a zero-valued object**: a zero score would say the website
   * failed every check where the truth is that nobody has looked (I10). That
   * case arrives as no figure plus a `locked` state.
   */
  figure?: Figure | null
  /**
   * The stored sentence, when one still describes the figure above it.
   *
   * **A sibling of `figure`, not a field on it.** Every field on `Figure` is
   * either the calculator's output or the provenance that makes it checkable;
   * prose is neither — it is a model's output *about* that output, and nesting
   * it would make the figure object partly generated. They also have different
   * lifetimes: the figure is recomputed on every page load, the sentence is
   * stored and can be absent while the figure is present.
   *
   * **Absent rather than stale.** A sentence that describes an older
   * measurement is dropped by the API, not labelled — to a reader, "superseded"
   * and "never explained" both render as the button, and surfacing the
   * difference invites showing the old sentence anyway.
   */
  narration?: Narration | null
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

/**
 * One finding on the morning brief.
 *
 * `headline` is the check's own label and `detail` is the calculator's
 * evidence, both verbatim — the API does not negate the one or rewrite the
 * other, and neither does this client. "0 / 37 images" is a finding; "add alt
 * text" would be guidance nobody computed.
 */
export type BriefItem = {
  /** `unmeasured` sorts above every `check_failed`, whatever the cost: a
   *  missing measurement qualifies every number beneath it. */
  kind: 'unmeasured' | 'check_failed'
  headline: string
  detail: string
  /** Points this check was worth. `0` for `unmeasured`, where nothing was
   *  scored and a number would be invented. */
  cost: number
  check_id: string
  capability_id: string
  method: string
}

/**
 * The morning brief — ADR 0029.
 *
 * Computed in code, so it costs nothing, cannot refuse, and behaves the same
 * with no API key configured. Ranked by points lost; it reports what was
 * **found** and never what changed, because nothing re-crawls yet.
 */
export type Brief = {
  /**
   * `not_measured` is not `all_held` with zeroes in it. An audit that never ran
   * must not read as one that found nothing, so the region is never hidden and
   * never shows a zero (I10).
   */
  state: 'findings' | 'all_held' | 'not_measured'
  items: BriefItem[]
  /** Server-authored, never empty. One wording change reaches every surface. */
  message: string
  points_held: number
  points_total: number
  checks_passed: number
  checks_total: number
  /** Empty only when nothing was measured. */
  measured_on: string
}

/**
 * Where the product is for this company — ADR 0030.
 *
 * Three counts, never a percentage. A percentage of "done" invites being read
 * as a verdict on the business, and the three bands have different remedies:
 * `not_built` is ours, and the other two are already working.
 */
export type Coverage = {
  measuring: number
  /** Reachable and not a measurement — the Setup and Watchlist tabs. Kept
   *  apart because a number somebody typed and a number we measured must never
   *  look alike. */
  reading_back: number
  /** Ours. No connection the customer makes switches one of these on. */
  not_built: number
  /** Tiles only; shared with the API's other two coverage counters. */
  total: number
}

/** One question still open, and what answering it would change. */
export type OpenQuestion = {
  key: string
  department: string
  /** The bank's own wording — the question here has to be the question setup
   *  will ask, or a founder who answers one has not answered the other. */
  prompt: string
  /** What the answer is for, from the bank. A question with no stated purpose
   *  is a form field (doc 06). */
  why: string
  consumed_by: string
  consumer_name: string
}

/**
 * What is open on the founder's side — `doc/14` step 5.
 *
 * **Answering informs; it does not unlock.** Every fact-consuming tile also
 * requires a source, so no question switches a tile on by itself. The split is
 * what makes that honest: `changes_a_figure` moves a number already on the
 * page, and the rest are waiting on us.
 */
export type OpenQuestions = {
  changes_a_figure: OpenQuestion[]
  /** Counted, not listed — a founder cannot act on these yet, and a long list
   *  would bury the ones they can. */
  waiting_on_us: number
  total: number
}

/**
 * One department, as the common surface summarises it — `doc/14` step 6.
 *
 * The tab rail, demoted to a block a reader passes on the way somewhere else.
 * Four states, because four different sentences are true, and a state whose
 * sentence is wrong is worse than no row: telling somebody to answer questions
 * for a department whose questions are all answered sends them looking for a
 * form that is not there.
 */
export type DirectorRow = {
  department: string
  label: string
  path: string
  measuring: number
  unanswered: number
  state: 'measuring' | 'answerable' | 'waiting' | 'empty'
  /** Server-authored, never empty. */
  line: string
}

/** Everything the common surface needs, in one response. */
export type Surface = {
  brief: Brief
  coverage: Coverage
  questions: OpenQuestions
  directors: DirectorRow[]
  /** The tiles that carry a figure, served exactly as the director page serves
   *  them. The surface changes where a founder reads a number, never what it
   *  says — asserted end to end in `test_surface_tiles.py`. */
  measured: DirectorBlock[]
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

export async function fetchSurface(): Promise<Surface> {
  return (await get('/api/dashboards/surface')) as Surface
}

export async function fetchDirector(department: string): Promise<Director> {
  return (await get(`/api/dashboards/${encodeURIComponent(department)}`)) as Director
}

/**
 * Ask a director to explain one figure.
 *
 * **A POST, and it carries CSRF**, because it spends tokens. A GET that spent
 * money would break the promise `require_csrf` relies on to exempt safe methods
 * — and a page load that quietly billed the customer for seven sentences
 * nobody asked for is the version of this feature that cannot be undone.
 *
 * `key` is the capability id exactly as it arrived in `DirectorBlock.key`.
 * Nothing is composed here from a department plus a block name: two ways to
 * name one thing is two ways to disagree about it, and the API refuses a key
 * that does not belong to the department in the path.
 *
 * A refusal is a **200 with a reason**, not a thrown error. There is a real
 * number on the screen beside it, and pushing this into a catch block is what
 * tempts a client to render an error state over a figure that is perfectly
 * good.
 */
export async function narrateBlock(
  department: string,
  key: string,
): Promise<NarrationResult> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const token = csrfToken()
  if (token) headers['X-CSRF-Token'] = token

  const response = await fetch(
    `/api/dashboards/${encodeURIComponent(department)}/narrate`,
    {
      method: 'POST',
      headers,
      body: JSON.stringify({ key }),
      credentials: 'same-origin',
      cache: 'no-store',
    },
  )

  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    throw new AuthError(
      messageFrom(payload, 'Could not write that explanation.'),
      response.status,
    )
  }
  return payload as NarrationResult
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
