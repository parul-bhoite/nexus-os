'use client'

import { useState } from 'react'
import {
  STATE_LABEL,
  narrateBlock,
  type AmountFigure,
  type BlockKind,
  type CountFigure,
  type DirectorBlock,
  type Narration,
  type ScoreFigure,
  type WidgetState,
} from '@/lib/dashboard-client'

/**
 * One capability on the rail, in whatever state it is actually in.
 *
 * `doc/13` §7. Eight states, and **each one has to tell the reader something
 * different to do** — two states that produce the same action should be one
 * state, and a state whose action is wrong is worse than no tile at all. That
 * is the rule this component exists to hold, and the reason the copy lives here
 * rather than in nine block components that would each drift.
 *
 * ## The value slot, and why it took until now
 *
 * This section used to be called *"why there is no value slot yet"*, and its
 * argument was right: nothing computed a number, so a value area would have
 * been an outline, and `dashboards.py` is explicit that a widget outline is the
 * thing a screenshot cannot distinguish from a working one.
 *
 * Two capabilities now carry a real figure — `marketing.seo_gaps` and
 * `marketing.brand_intelligence`, scored by `calculators/audit.py` from a
 * crawled page. **The slot appears only when `block.figure` is present**, so
 * the other eighty-eight tiles render exactly as before. The outline rule is
 * unchanged; there is simply something to put in it.
 *
 * Three things the figure renders, and each is load-bearing:
 *
 * - **The denominator, next to the score.** `45 / 65 points`, not `69%`. A
 *   percentage reads as "69% of your SEO is fine", which is a much stronger
 *   claim than "you passed 45 of 65 weighted points" — and the second is what
 *   was computed. The percentage is served and available; it is not the
 *   headline.
 * - **What it measures.** `figure.measures` names what was counted *and what
 *   was not*, because a tile called "Brand Intelligence" promising voice
 *   consistency, showing a legibility score, would be a correct number under a
 *   misdescribing headline. That is the one dishonest thing this could ship.
 * - **The date the page was fetched.** Standing in for the `stale` state the
 *   route deliberately does not reach: nothing re-crawls on a schedule, so
 *   deriving staleness would mark every audit out of date a week after signup.
 *
 * ## The sentence sits with the number, not with the consequence
 *
 * A narration is a gloss on the figure, so it goes on the figure's side of the
 * line this file already draws: figure, then sentence, then "needs keyword
 * data". Put below the consequence it would read as a footnote to a footnote.
 * Not inside the working drawer either — the drawer is the arithmetic, the
 * sentence is a reading of it, and a reader who wants one rarely wants the
 * other.
 *
 * **It is a button, never automatic.** A page load that wrote seven sentences
 * would spend the founder's daily allowance on tiles nobody looked at, and a
 * GET that spends money breaks the promise `require_csrf` relies on when it
 * exempts safe methods.
 *
 * ## The working drawer needs no endpoint
 *
 * `figure.checks` **is** the calculator's working — nine observations, each
 * with the points it contributed and the evidence behind it. So the drawer that
 * was reserved-and-disabled now opens, with no new route and no `generation`
 * row to read. A narrated sentence would need that row; a number's arithmetic
 * does not.
 *
 * ## The three rules that are easiest to lose
 *
 * - **`warming` never asks for a connection.** Telling somebody to connect what
 *   they already connected is how a product loses trust in its own
 *   instructions. It gets a date, not an instruction.
 * - **`self_reported` is never a metric.** `doc/05` §0 requires that a number
 *   they typed and a number we measured never look identical, so this renders
 *   as quotation with an attribution rather than as a figure.
 * - **`planned` carries no call to action.** An unbuilt widget cannot be
 *   unlocked by connecting anything, and offering an unlock would be a promise
 *   the product then breaks.
 */

const STATE_STYLES: Record<WidgetState, string> = {
  live: 'bg-steel-100 text-steel-700',
  partial: 'bg-gold-200 text-clay-600',
  locked: 'bg-clay-100 text-clay-600',
  warming: 'bg-gold-100 text-clay-600',
  self_reported: 'bg-bone-200 text-ink-600',
  stale: 'bg-clay-100 text-clay-600',
  unavailable: 'bg-bone-200 text-ink-500',
  planned: 'bg-bone-200 text-ink-500',
}

/**
 * What each kind will draw. Present tense for the ones that exist, and
 * deliberately concrete: "four lanes with every order named" is checkable and
 * "operational data" is not.
 */
const KIND_PROMISE: Record<BlockKind, string> = {
  metric: 'A figure with its delta, its sources, and the arithmetic behind it.',
  trend: 'A series over twelve periods, once there are twelve to compare.',
  table: 'Rows with their computed columns, and a dash where there is nothing to divide by.',
  board: 'Lanes with every item named — no percentage this cannot itemise.',
  cards: 'Ranked items, each with the evidence that produced it.',
  queue: 'What is waiting on somebody, and how long it has waited.',
  facts: 'What you told us, in your words, with the date you said it.',
  panel: 'A named finding, carrying the inputs it was drawn from.',
  studio: 'A draft you can edit, with every claim cited to its source.',
}

/**
 * Whether this state means a figure is on screen.
 *
 * The three that do are the three where the working drawer has something to
 * open. `self_reported` is deliberately not among them: it carries a value and
 * it is not a measurement, which is the whole point of the distinction.
 *
 * Kept as a state question even though `block.figure` now answers the same
 * thing more directly, because the two answer it for different reasons and
 * both must agree: a state in this set with no figure is a serving bug, and a
 * figure outside it would be a number the state machine says we should not
 * have. The render below requires *both*.
 */
function hasFigure(state: WidgetState): boolean {
  return state === 'live' || state === 'partial' || state === 'stale'
}

/**
 * The money a figure carries, formatted once and in one place.
 *
 * `Intl.NumberFormat` with the currency the API served, from minor units. The
 * API serves `percentage` rather than letting clients divide, for the reason
 * `FigureOut` gives — two clients must not round differently — and money has
 * more ways to differ than a percentage does, so the same discipline applies:
 * one function, not a template literal at each call site.
 */
function money(totalMinor: number, currency: string): string {
  return new Intl.NumberFormat(undefined, {
    style: 'currency',
    currency,
    maximumFractionDigits: 0,
  }).format(totalMinor / 100)
}

/** A scored audit: the figure, its denominator, and how many checks stand behind it. */
function ScoreFigureBody({ figure }: { figure: ScoreFigure }) {
  return (
    <>
      <p className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <span className="font-display text-3xl leading-none text-ink-900">
          {figure.score}
          <span className="text-ink-400"> / {figure.max_score}</span>
        </span>
        <span className="text-sm text-ink-500">
          points · {figure.checks_passed} of {figure.checks.length} checks passed
        </span>
      </p>

      {/* What was counted, and what was not. The guard against a real number
          under a headline that promises more than it measured. */}
      <p className="mt-2 max-w-prose text-sm leading-relaxed text-ink-600">
        <span className="font-medium text-ink-700">{figure.label}.</span> {figure.measures}
      </p>

      <p className="mt-2 text-sm text-ink-400">
        Measured {figure.measured_at} from{' '}
        <a
          href={figure.source_url}
          target="_blank"
          rel="noreferrer noopener"
          className="underline decoration-ink-300 underline-offset-2 hover:text-ink-600"
        >
          {figure.source_url}
        </a>
      </p>
    </>
  )
}

/**
 * A counted, totalled figure — ADR 0033's second kind.
 *
 * **No denominator, and none drawn.** The scored body reads `30 / 65`; this one
 * cannot, because a pipeline is not a fraction of anything. Borrowing that
 * layout and putting the count where a denominator goes would read as one, which
 * is the whole reason the two are separate components rather than one with
 * optional fields.
 *
 * **`total_minor === null` is not zero.** It means nothing could be totalled —
 * no priced items, or two currencies — and the count is still true, so the count
 * leads and the absence is stated rather than rendered as a figure of zero (I10).
 */
function AmountFigureBody({ figure }: { figure: AmountFigure }) {
  const totalled = figure.total_minor !== null && figure.currency !== null

  return (
    <>
      <p className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <span className="font-display text-3xl leading-none text-ink-900">
          {totalled ? money(figure.total_minor as number, figure.currency as string) : figure.count}
        </span>
        <span className="text-sm text-ink-500">
          {totalled
            ? `across ${figure.count} ${figure.count === 1 ? 'deal' : 'deals'}`
            : `${figure.count === 1 ? 'deal' : 'deals'} — no total, because nothing here could be added up`}
        </span>
      </p>

      <p className="mt-2 max-w-prose text-sm leading-relaxed text-ink-600">
        <span className="font-medium text-ink-700">{figure.label}.</span> {figure.measures}
      </p>

      {figure.uncounted > 0 ? (
        /* Part of the figure, not a footnote: a total that did not say what it
           left out is a total presented as complete. */
        <p className="mt-2 text-sm text-clay-600">
          {figure.uncounted} of these {figure.uncounted === 1 ? 'is' : 'are'}{' '}
          {figure.uncounted_label}, so {figure.uncounted === 1 ? 'it is' : 'they are'} counted
          and not added.
        </p>
      ) : null}

      <p className="mt-2 text-sm text-ink-400">
        Read {figure.measured_at} from your {figure.source}
      </p>
    </>
  )
}

/**
 * Counts over the customer's own records — ADR 0034's third kind.
 *
 * **A different body, not a badge.** `doc/13` §7 requires that a number
 * somebody typed and a number we measured never look identical, and says a
 * badge on an otherwise identical tile fails that at a glance and in a
 * screenshot. So this reads as a tally of a record rather than as a
 * measurement: the lead figure is the population, the breakdown is counts, and
 * the provenance line says who wrote them down.
 *
 * **Nothing is divided.** There is no ratio on screen and none computed here —
 * `open / recorded` would be the exact percentage over a partial record the
 * whole kind exists to refuse, and it would be one line of arithmetic away in
 * any component that had the two numbers and a habit.
 */
function CountFigureBody({ figure }: { figure: CountFigure }) {
  return (
    <>
      <p className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <span className="font-display text-3xl leading-none text-ink-900">{figure.recorded}</span>
        <span className="text-sm text-ink-500">
          {figure.noun} recorded, {figure.open_items} still open
        </span>
      </p>

      <p className="mt-2 max-w-prose text-sm leading-relaxed text-ink-600">
        <span className="font-medium text-ink-700">{figure.label}.</span> {figure.measures}
      </p>

      {figure.overdue > 0 ? (
        <p className="mt-2 text-sm text-clay-600">
          {figure.overdue} {figure.overdue === 1 ? 'is' : 'are'} past a date you set.
        </p>
      ) : null}

      {figure.undated > 0 ? (
        /* Said plainly rather than folded into "on track". Nobody named a day,
           so nothing is late — and a reader weighing the overdue count needs to
           know how many could never have been counted in it. */
        <p className="mt-1 text-sm text-ink-500">
          {figure.undated} {figure.undated === 1 ? 'has' : 'have'} no due date, so{' '}
          {figure.undated === 1 ? 'it is' : 'they are'} never counted as late.
        </p>
      ) : null}

      <p className="mt-2 text-sm text-ink-400">
        Counted from what your workspace recorded, last updated {figure.recorded_at}
      </p>
    </>
  )
}

/** Whichever kind this tile carries. */
function Figure({ block }: { block: DirectorBlock }) {
  const figure = block.figure
  if (!figure) return null

  return (
    <div className="mt-4">
      {figure.kind === 'score' ? (
        <ScoreFigureBody figure={figure} />
      ) : figure.kind === 'amount' ? (
        <AmountFigureBody figure={figure} />
      ) : (
        <CountFigureBody figure={figure} />
      )}
    </div>
  )
}

/**
 * The working, opened.
 *
 * Every check the calculator ran, in its order, with the points it contributed
 * and the evidence it saw. Failures are not styled as errors: a page without
 * structured data has not done anything wrong, and colouring nine rows red
 * would turn an observation into a reprimand.
 */
function Working({
  block,
  narration,
}: {
  block: DirectorBlock
  narration: Narration | null
}) {
  const [open, setOpen] = useState(false)
  const figure = block.figure
  if (!figure) return null

  return (
    <div className="mt-4">
      <button
        type="button"
        onClick={() => setOpen((was) => !was)}
        aria-expanded={open}
        className="self-start rounded-lg border border-ink-200 px-3 py-1.5 text-sm font-medium text-ink-700 hover:border-ink-300 hover:text-ink-900"
      >
        {open ? '− why this number' : '+ why this number'}
      </button>

      {open ? (
        <div className="mt-3 overflow-hidden rounded-xl border border-ink-100">
          {/* A scored audit's working is its checks. An amount figure has none —
              a pipeline is a sum of rows, not nine weighted observations — and
              inventing a checklist to fill the space would be the drawer showing
              working that never happened. It gets the counts it was built from
              and the method, which is the whole of its arithmetic. */}
          <ul className="divide-y divide-ink-100">
            {figure.kind === 'amount' ? (
              <li className="flex flex-wrap gap-x-3 gap-y-1 px-4 py-2.5 text-sm">
                <span className="min-w-0 grow">
                  <span className="text-ink-800">
                    {figure.count} counted, {figure.count - figure.uncounted} added
                  </span>
                  <span className="mt-0.5 block text-ink-500">
                    {figure.uncounted > 0
                      ? `${figure.uncounted} ${figure.uncounted_label}, so counted and not added.`
                      : `Every one of them is priced, so all ${figure.count} are in the total.`}
                  </span>
                </span>
              </li>
            ) : null}
            {figure.kind === 'count' ? (
              /* A census has no checks either. Its whole arithmetic is the
                 partition — done plus open, and open split into late, undated
                 and still to come — so the drawer shows that it adds up rather
                 than inventing a checklist to fill the space. */
              <li className="flex flex-wrap gap-x-3 gap-y-1 px-4 py-2.5 text-sm">
                <span className="min-w-0 grow">
                  <span className="text-ink-800">
                    {figure.recorded} recorded, {figure.recorded - figure.open_items} done,{' '}
                    {figure.open_items} open
                  </span>
                  <span className="mt-0.5 block text-ink-500">
                    Of the {figure.open_items} open, {figure.overdue} past a date and{' '}
                    {figure.undated} with no date.
                  </span>
                </span>
              </li>
            ) : null}
            {(figure.kind === 'score' ? figure.checks : []).map((check) => (
              <li key={check.id} className="flex flex-wrap gap-x-3 gap-y-1 px-4 py-2.5 text-sm">
                <span
                  className={`shrink-0 font-mono text-2xs uppercase tracking-[0.08em] ${
                    check.passed ? 'text-steel-600' : 'text-ink-400'
                  }`}
                >
                  {check.passed ? `+${check.weight}` : `0 / ${check.weight}`}
                </span>
                <span className="min-w-0 grow">
                  <span className="text-ink-800">{check.label}</span>
                  {/* The calculator's own words. An observation, never advice. */}
                  <span className="mt-0.5 block text-ink-500">{check.evidence}</span>
                </span>
              </li>
            ))}
          </ul>
          <p className="border-t border-ink-100 bg-bone-50 px-4 py-2 font-mono text-2xs text-ink-400">
            {figure.method}
            {/* Which `SKILL.md` wrote the sentence above, beside the arithmetic
                that produced the number. A disputed sentence should trace back
                to its instructions as readily as a disputed figure traces back
                to its working — otherwise the prose is the one thing on the
                tile with no provenance at all. */}
            {narration ? (
              <span className="block">explained by narrate-metric {narration.prompt_version}</span>
            ) : null}
          </p>
        </div>
      ) : null}
    </div>
  )
}

/**
 * The reasons that mean asking again is pointless.
 *
 * The button is **hidden** for these rather than disabled. A disabled button
 * reads as broken and invites a support conversation about the wrong thing; an
 * absent one, beside a score that has not changed, reads as "this deployment
 * does not do that" — which is what ADR 0011 says a missing key actually is.
 */
const NOTHING_TO_RETRY: ReadonlySet<string> = new Set([
  'model_unavailable',
  'skill_disabled',
  'budget_exhausted',
])

/**
 * The reasons where trying again is the honest suggestion.
 *
 * `invented_number` is in here deliberately. It means the guard caught a model
 * stating a figure no calculation produced — the system working, not failing —
 * and a second attempt usually succeeds.
 */
const WORTH_RETRYING: ReadonlySet<string> = new Set([
  'provider_failed',
  'schema_invalid',
  'invented_number',
])

/**
 * The sentence, and the one control that writes it.
 *
 * Every word the reader sees on a refusal is the server's `message`. There is
 * no reason-to-sentence map here, for the reason `unlock` already gives: one
 * wording change has to reach every surface, and a screen must not be able to
 * ship with the space drawn and the copy forgotten.
 *
 * Refusals render in `text-ink-500`, not `text-clay-600`. This file reserves
 * clay for calls to action about the *data*, and a refusal about the
 * *explanation* is not one — the number beside it is fine and must not start
 * reading as though it were in doubt.
 */
function Explanation({
  block,
  department,
  narration,
  onNarration,
}: {
  block: DirectorBlock
  department: string
  narration: Narration | null
  onNarration: (narration: Narration) => void
}) {
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [reason, setReason] = useState('')
  const [superseded, setSuperseded] = useState(false)

  const figure = block.figure
  if (!figure) return null

  // **Scores only, stated here rather than trusted from the call site.** The
  // button is already gated on `kind === 'score'` where this is mounted, and
  // that gate is invisible from inside — `result.measured_at` below reads a
  // field only a scored figure has, so adding ADR 0034's count kind broke the
  // compile here and not at the gate. Narrowing in the component means the
  // precondition travels with the code that depends on it.
  if (figure.kind !== 'score') return null

  // Read out here, not inside `explain`. TypeScript does not carry the narrowing
  // above into a hoisted function declaration — which is what the redundant
  // `figure &&` in the old comparison was working around — so the closure took
  // `Figure` and lost the field.
  const measuredAt = figure.measured_at

  async function explain() {
    setBusy(true)
    setMessage('')
    setReason('')
    setSuperseded(false)
    try {
      const result = await narrateBlock(department, block.key)

      // The page was re-crawled between load and click. The sentence is true
      // about a number the reader cannot see, and showing it beside the one
      // they can is the single way this feature can state something false.
      if (result.measured_at !== measuredAt) {
        setSuperseded(true)
        return
      }

      if (result.outcome === 'answered' && result.narration) {
        onNarration(result.narration)
        return
      }
      setReason(result.reason)
      setMessage(result.message)
    } catch (error) {
      // A transport failure, not a refusal — the API never got to have an
      // opinion. Kept out of `reason` so the button stays offered.
      setMessage(error instanceof Error ? error.message : 'Could not write that explanation.')
    } finally {
      setBusy(false)
    }
  }

  const label = busy
    ? 'Writing…'
    : WORTH_RETRYING.has(reason)
      ? 'Try again'
      : narration
        ? 'Explain again'
        : 'Explain this score'

  return (
    <div className="mt-3">
      {narration ? (
        <p className="max-w-prose text-[0.95rem] leading-relaxed text-ink-700">
          {narration.prose}
        </p>
      ) : null}

      {superseded ? (
        <p className="mt-2 max-w-prose text-sm leading-relaxed text-ink-500">
          This score has changed since the page loaded. Reload to see it.
        </p>
      ) : message ? (
        <p className="mt-2 max-w-prose text-sm leading-relaxed text-ink-500">{message}</p>
      ) : null}

      {NOTHING_TO_RETRY.has(reason) ? null : (
        <button
          type="button"
          onClick={explain}
          disabled={busy}
          aria-busy={busy}
          className={`mt-2 self-start rounded-lg px-3 py-1.5 text-sm font-medium disabled:cursor-not-allowed ${
            narration
              ? // Quiet once there is a sentence. Re-narrating spends tokens,
                // so it must not be the dominant control on the tile.
                'text-ink-500 underline decoration-ink-300 underline-offset-2 hover:text-ink-700'
              : 'border border-ink-200 text-ink-700 hover:border-ink-300 hover:text-ink-900'
          }`}
        >
          {label}
        </button>
      )}
    </div>
  )
}

function Consequence({ block }: { block: DirectorBlock }) {
  switch (block.state) {
    case 'locked':
    case 'partial':
      // Doc 04 §6 rule 1: the tile is a call to action, not a failure. The
      // sentence comes from the API so one wording change reaches every
      // surface, and so a tile cannot ship with the outline drawn and the
      // sentence forgotten.
      return block.unlock ? (
        <p className="mt-3 text-sm font-medium text-clay-600">{block.unlock}</p>
      ) : null

    case 'warming':
      return (
        <p className="mt-3 text-sm font-medium text-clay-600">
          Connected. Not enough history to compare against yet — nothing to do but wait.
        </p>
      )

    case 'stale':
      return (
        <p className="mt-3 text-sm font-medium text-clay-600">
          This figure is real and out of date. Its age is shown with it, because a
          number from last quarter reads as current unless it says otherwise.
        </p>
      )

    case 'unavailable':
      return (
        <p className="mt-3 text-sm font-medium text-clay-600">
          We could not compute this. The reason is recorded against the attempt rather
          than guessed at here.
        </p>
      )

    case 'self_reported':
      return (
        <p className="mt-3 text-sm text-ink-500">
          Your own answer, not a measurement. It will be compared against the real
          figure when the source that measures it is connected.
        </p>
      )

    case 'planned':
      // No unlock, deliberately. `locked` invites you to connect something;
      // `planned` admits the widget does not exist, and dressing it as the
      // first would be a promise the product cannot keep.
      return null

    case 'live':
      return null
  }
}

export function BlockCard({
  block,
  department,
}: {
  block: DirectorBlock
  department: string
}) {
  const dimmed = block.state === 'planned'

  // Seeded from the served payload and updated from the POST — **never
  // re-fetched**. Re-reading the director to pick up one sentence would
  // recompute both figures and flicker the whole rail.
  const [narration, setNarration] = useState<Narration | null>(block.narration ?? null)

  return (
    <li
      className={`flex flex-col rounded-2xl border px-5 py-5 shadow-paper transition-colors ${
        dimmed ? 'border-ink-100 bg-bone-50' : 'border-ink-100 bg-white'
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <h3 className="font-display text-lg leading-snug text-ink-900">{block.name}</h3>
        <span
          className={`shrink-0 rounded-full px-2.5 py-1 font-mono text-2xs uppercase tracking-[0.08em] ${
            STATE_STYLES[block.state]
          }`}
        >
          {STATE_LABEL[block.state]}
        </span>
      </div>

      <p className="mt-2 text-[0.95rem] leading-relaxed text-ink-600">{block.shows}</p>

      {/* Above the consequence, deliberately. The number is what this tile is
          for; "needs keyword data" qualifies it and reads as a footnote to it,
          where the reverse order reads as an error with a number attached. */}
      <Figure block={block} />

      {/* Between the figure and the consequence: a gloss on the number belongs
          on the number's side of that line. Both conditions again, for the same
          reason the drawer gives below. */}
      {/* **Scored figures only** (ADR 0033). `narrate-metric` speaks in
          numerator and denominator, so a pipeline sentence grounded in those
          keys would be grounded in nothing — and the API refuses the capability
          with a 404. A button that is there to press and cannot work is worse
          than an absent one, which is the same argument `NOTHING_TO_RETRY`
          already makes about a disabled control. */}
      {hasFigure(block.state) && block.figure?.kind === 'score' ? (
        <Explanation
          block={block}
          department={department}
          narration={narration}
          onNarration={setNarration}
        />
      ) : null}

      <Consequence block={block} />

      {/* Both conditions, not either. A state in `hasFigure` with no figure is
          a serving bug and must not render a drawer onto nothing; a figure
          arriving in a state the machine says should not carry one is a number
          we were told we should not have. Requiring both means neither is
          papered over. */}
      {hasFigure(block.state) && block.figure ? (
        <Working block={block} narration={narration} />
      ) : (
        <p className="mt-4 text-sm leading-relaxed text-ink-400">
          {KIND_PROMISE[block.block]}
        </p>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-ink-100 pt-3">
        {/* The paragraph that specified it, kept so a tile on a screen can be
            traced back to the document. Absent for the thirteen capabilities
            doc 08 specified and doc 05 never did. */}
        {block.doc05_id ? (
          <span className="font-mono text-2xs uppercase tracking-[0.1em] text-ink-400">
            {block.doc05_id}
          </span>
        ) : null}
        <span className="font-mono text-2xs tracking-[0.04em] text-ink-400">{block.key}</span>
        <span className="rounded-full border border-ink-200 px-2 py-0.5 font-mono text-2xs uppercase tracking-[0.08em] text-ink-500">
          {block.block}
        </span>
      </div>
    </li>
  )
}
