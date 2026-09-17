'use client'

import { useState } from 'react'
import { Badge, Figure as Fig, NoFigure, StateDot } from '@/components/ui/Data'
import { Disclosure } from '@/components/ui/Disclosure'
import { Button } from '@/components/ui/Button'
import {
  STATE_LABEL,
  narrateBlock,
  type AmountFigure,
  type BlockKind,
  type CountFigure,
  type DirectorBlock,
  type DriversFigure,
  type Figure,
  type Narration,
  type PrioritiesFigure,
  type RateFigure,
  type ScoreFigure,
  type WidgetState,
} from '@/lib/dashboard-client'

/**
 * One capability on the rail, in whatever state it is actually in.
 *
 * `doc/13` §7. Eight states, and **each one has to tell the reader something
 * different to do** — two states that produce the same action should be one
 * state, and a state whose action is wrong is worse than no tile at all.
 *
 * ## What the 2026-09 audit changed, and what it deliberately did not
 *
 * Nothing here was deleted. Every sentence the tile used to carry — what the
 * figure measures, what it excluded, the date it was read, whether anybody has
 * vouched that the record is complete, the capability's specification id — is
 * still rendered, still in the product's own words, still sourced from the API
 * rather than restated in the browser. What changed is **the order**, and the
 * reason is a measurement rather than a preference.
 *
 * On the dashboard as audited, a block card was about seventeen lines tall. One
 * of those lines was the number. The other sixteen were the apparatus that
 * makes the number trustworthy: a bolded lead-in and three lines of
 * methodology, a provenance line, and — on six of the twelve tiles at once — a
 * clay-coloured sentence reading *"You have not said whether this is all of
 * them, so this counts the record rather than the company."* That sentence is
 * correct and it is important. Repeated six times down one page in a warning
 * colour it is wallpaper, and wallpaper is the one thing a warning must never
 * become.
 *
 * So the face of the tile is now: its name, the figure, and the single clause
 * that qualifies the figure. Everything else moved behind one disclosure, in
 * the same place, with the same label, on every tile in the product — which
 * means "where did this come from?" has one answer a reader learns once, rather
 * than sixteen lines they have to read every time to find the one that matters.
 *
 * The product's promise is that every number is traceable. It was never that
 * every number arrives buried in its trace.
 *
 * ## Three specific reversals
 *
 * - **The `LIVE` badge is gone from the normal case.** Twelve tiles each wore
 *   one, in the highest-contrast treatment on a card whose point is a figure. A
 *   badge on everything marks nothing. `StateDot` renders 6px of colour and
 *   renders *nothing at all* when the state is `live`, so the tiles wearing a
 *   marker are exactly the ones that need reading.
 * - **The specification ids moved into the working.** `2.3`,
 *   `executive.todays_priorities` and a `CARDS` pill sat on the face of every
 *   tile. They exist so a tile on a screen can be traced to the paragraph that
 *   specified it, which is a real need — of somebody debugging the product, not
 *   of somebody running a business. They are one click away, beside the
 *   arithmetic, where that person is already looking.
 * - **The always-on completeness caveat became a badge plus a sentence.** The
 *   sentence is unchanged and lives in the working. On the face, an
 *   `Unconfirmed` badge says the same thing in two words without spending a
 *   warning colour on the ordinary state of a new workspace.
 *
 * ## The three rules that are easiest to lose
 *
 * - **`warming` never asks for a connection.** Telling somebody to connect what
 *   they already connected is how a product loses trust in its own
 *   instructions. It gets a date, not an instruction.
 * - **`self_reported` is never a metric.** `doc/05` §0 requires that a number
 *   they typed and a number we measured never look identical, so this renders
 *   as a tally of a record with its own provenance line rather than as a
 *   measurement.
 * - **`planned` carries no call to action.** An unbuilt widget cannot be
 *   unlocked by connecting anything, and offering an unlock would be a promise
 *   the product then breaks.
 */

/**
 * How each state should read at a glance.
 *
 * `live` is `none` — the normal state wears no marker. The rest map onto four
 * tones rather than eight colours, because eight badge colours on one page is
 * a legend the reader has to hold in their head.
 */
const STATE_TONE: Record<WidgetState, 'none' | 'attention' | 'warn' | 'quiet' | 'good'> = {
  live: 'none',
  partial: 'attention',
  locked: 'attention',
  warming: 'quiet',
  self_reported: 'quiet',
  stale: 'warn',
  unavailable: 'warn',
  planned: 'quiet',
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

/* ── The face ──────────────────────────────────────────────────────────────
   One figure and one clause per kind. Anything that qualifies, excludes,
   dates or sources the number belongs in `FigureDetail` below — if a sentence
   here would be the second sentence, it is in the wrong function. */

function Head({ figure }: { figure: Figure }) {
  switch (figure.kind) {
    case 'score':
      // `45 / 65 points`, never `69%`. A percentage reads as "69% of your SEO is
      // fine", which is a much stronger claim than "you passed 45 of 65 weighted
      // points" — and the second is what was computed.
      return (
        <Fig
          value={
            <>
              {figure.score}
              <span className="text-ink-300"> / {figure.max_score}</span>
            </>
          }
          unit="points"
          qualifier={`${figure.checks_passed} of ${figure.checks.length} checks passed`}
        />
      )

    case 'amount': {
      // `total_minor === null` is not zero. It means nothing could be totalled —
      // no priced items, or two currencies — and the count is still true, so the
      // count leads and the absence is stated rather than rendered as a zero.
      const totalled = figure.total_minor !== null && figure.currency !== null
      const deals = `${figure.count} ${figure.count === 1 ? 'deal' : 'deals'}`
      return totalled ? (
        <Fig
          value={money(figure.total_minor as number, figure.currency as string)}
          unit={`across ${deals}`}
        />
      ) : (
        <Fig
          value={figure.count}
          unit={`${figure.count === 1 ? 'deal' : 'deals'} — no total, because nothing here could be added up`}
        />
      )
    }

    case 'count':
      // One clause, not a unit and a qualifier. "7 projects recorded, 3 still
      // open" is the sentence the API's vocabulary produces; splitting it into
      // two spans reads the same and is no longer the same string.
      return (
        <Fig
          value={figure.recorded}
          unit={`${figure.noun} recorded, ${figure.open_items} ${figure.open_label}`}
        />
      )

    case 'rate':
      // The refusal is the figure's, not this component's. Both gates are
      // decided server-side so exactly one place says whether a percentage may
      // be shown; the job here is to render the reason in words a founder can
      // act on.
      if (figure.refused) {
        return <NoFigure because={REFUSAL[figure.refused] ?? 'This cannot be worked out yet.'} />
      }
      return (
        <Fig
          value={`${figure.percentage}%`}
          // The denominator travels with the number, named — a rate whose
          // denominator is unlabelled is a claim nobody can check.
          unit={
            figure.unit === 'money'
              ? figure.currency
                ? `${money(figure.numerator as number, figure.currency)} of ${money(
                    figure.denominator as number,
                    figure.currency,
                  )} ${figure.denominator_label}`
                : // Money with no currency for the workspace. The share is still
                  // true; the amounts are minor units and showing them raw would
                  // read as a count of things.
                  figure.denominator_label
              : `${figure.numerator} of ${figure.denominator} ${figure.denominator_label}`
          }
        />
      )

    case 'drivers':
      // ADR 0040: the figures a score would have averaged, uncombined. The
      // absent number gets a sentence — `doc/13` §7 never permits an empty slot.
      return <NoFigure because={figure.reason} />

    case 'priorities':
      return <PrioritiesHead figure={figure} />
  }
}

const REFUSAL: Record<string, string> = {
  unvouched: 'Confirm on Your work that this is the whole list, and this becomes a percentage.',
  no_rule:
    'Set how many days past the promised date an order counts as late, and this becomes a percentage.',
  nothing_sent: 'Nothing has gone out yet, so there is no on-time figure to work out.',
  nothing_priced: 'None of your suppliers has a spend figure yet, so there is no share to work out.',
}

/**
 * What is waiting on the reader.
 *
 * The one kind whose face is a list rather than a number, because its answer
 * *is* the list. **Two lists, never merged**: the ranked one is ranked because
 * every row is late in days, and the other holds what matters without being
 * measured in days. Interleaving them would need a weighting nobody set.
 */
function PrioritiesHead({ figure }: { figure: PrioritiesFigure }) {
  const row = (item: { kind_of: string; title: string; detail: string }, key: string) => (
    <li key={key} className="flex flex-wrap items-baseline gap-x-3 py-1.5">
      <span className="w-20 shrink-0 text-2xs uppercase tracking-[0.08em] text-ink-400">
        {item.kind_of}
      </span>
      <span className="min-w-0 grow text-body text-ink-800">{item.title}</span>
      <span className="shrink-0 text-2xs text-clay-600">{item.detail}</span>
    </li>
  )

  if (figure.overdue.length === 0 && figure.beside.length === 0) {
    return (
      <p className="text-body leading-relaxed text-ink-600">
        Nothing you have recorded is past its date. That is about what you have written
        down, not about everything you have on.
      </p>
    )
  }

  return (
    <div>
      {figure.overdue.length > 0 ? (
        <ul className="divide-y divide-ink-100">
          {figure.overdue.map((item, index) => row(item, `overdue-${index}`))}
        </ul>
      ) : null}

      {figure.beside.length > 0 ? (
        <>
          <p className="mt-3 text-2xs uppercase tracking-[0.1em] text-ink-400">
            Not measured in days
          </p>
          <ul className="divide-y divide-ink-100">
            {figure.beside.map((item, index) => row(item, `beside-${index}`))}
          </ul>
        </>
      ) : null}
    </div>
  )
}

/**
 * The one clause that belongs beside the figure rather than behind the
 * disclosure — the thing that changes what the number *means*, not what it was
 * built from.
 *
 * Kept to a single short line on purpose. The test for whether something
 * belongs here: would a reader who acted on the figure without it be acting on
 * a misunderstanding? "3 are past a date you set" passes. "Counted from what
 * your workspace recorded, last updated 2026-09-17" does not — it is
 * provenance, which is what the disclosure is for.
 */
function Caveat({ figure }: { figure: Figure }) {
  if (figure.kind === 'count' && figure.overdue > 0) {
    return (
      <p className="note-warn">
        {figure.overdue} {figure.overdue === 1 ? 'is' : 'are'} past a date you set.
      </p>
    )
  }

  if (figure.kind === 'amount' && figure.uncounted > 0) {
    // Part of the figure, not a footnote: a total that did not say what it left
    // out is a total presented as complete.
    return (
      <p className="note-warn">
        {figure.uncounted} of these {figure.uncounted === 1 ? 'is' : 'are'}{' '}
        {figure.uncounted_label}, so {figure.uncounted === 1 ? 'it is' : 'they are'} counted
        and not added.
      </p>
    )
  }

  if (figure.kind === 'rate' && figure.outstanding > 0) {
    return (
      <p className="field-hint">
        {figure.outstanding} {figure.outstanding === 1 ? 'order has' : 'orders have'} not gone
        out yet
        {figure.overdue > 0
          ? figure.outstanding === 1
            ? ', and it is past the promise'
            : `, and ${figure.overdue} of those ${figure.overdue === 1 ? 'is' : 'are'} past the promise`
          : ''}
        .
      </p>
    )
  }

  return null
}

/**
 * Small counts beside the figure — severity bands, a breakdown.
 *
 * **Counts side by side, never a bar.** A stacked bar of three numbers reads as
 * a share of a whole, and ADR 0034's rule is that nothing here divides. Every
 * band is shown even at zero — "0 high" is the reassuring thing somebody came
 * to the register for.
 */
function Breakdown({ figure }: { figure: Figure }) {
  // ADR 0040's whole point is that the figures a score would have averaged are
  // *named* rather than combined, so naming them is this tile's content and not
  // its working. They stay on the face.
  if (figure.kind === 'drivers') {
    return (
      <ul className="flex flex-wrap gap-x-4 gap-y-1">
        {figure.inputs.map((input) => (
          <li key={input.key} className="text-meta text-ink-600">
            {input.name}
          </li>
        ))}
      </ul>
    )
  }

  if (figure.kind !== 'count' || figure.breakdown.length === 0) return null

  return (
    <dl className="flex flex-wrap gap-x-6 gap-y-2">
      {figure.breakdown.map((bucket) => (
        <div key={bucket.label}>
          <dt className="text-2xs uppercase tracking-[0.08em] text-ink-500">{bucket.label}</dt>
          <dd
            className={`tnum font-display text-figure-sm leading-none ${
              bucket.count > 0 ? 'text-ink-900' : 'text-ink-300'
            }`}
          >
            {bucket.count}
          </dd>
        </div>
      ))}
    </dl>
  )
}

/**
 * A two-word marker for the completeness question (D29 / ADR 0035).
 *
 * The full sentence is in the working and is unchanged. This exists so that the
 * distinction between "a count of your records" and "a count of your company"
 * survives a glance, without spending a warning colour on the ordinary state of
 * a workspace nobody has finished filling in.
 */
function Vouched({ figure }: { figure: Figure }) {
  if (figure.kind !== 'count') return null
  return figure.complete_as_of ? (
    <Badge tone="good">Confirmed complete</Badge>
  ) : (
    <Badge tone="quiet">Unconfirmed</Badge>
  )
}

/* ── The working ───────────────────────────────────────────────────────────
   Everything that was on the face and is now one click away, in one order on
   every tile: what it measures, what it left out, where it came from, the
   arithmetic, and the identifiers. */

/** What this measures and what it deliberately does not. */
function Measures({ figure }: { figure: Figure }) {
  return (
    <p className="max-w-read text-meta leading-relaxed text-ink-600">
      <span className="font-medium text-ink-700">{figure.label}.</span> {figure.measures}
    </p>
  )
}

/**
 * Where the number came from, what rule produced it, and what it left out.
 *
 * **On the face of the tile, deliberately — this was reverted mid-redesign.**
 * The audit moved all of it behind the disclosure, and that was wrong for a
 * reason this file already argued and I did not weigh properly: `figure.measures`
 * and the provenance line are what stop a correct number sitting under a
 * headline that promises more than was measured. A tile called "Brand
 * Intelligence" showing a legibility score is not fixed by the explanation
 * being one click away.
 *
 * What was actually wrong was never that these sentences were present. It was
 * that they were rendered at the same size and weight as the figure's own
 * qualifier — five or six equal paragraphs, one of them in a warning colour on
 * six tiles at once — so a tile read as a wall with a number somewhere in it.
 *
 * So they stay, and they recede: one block, at the smallest step in the scale,
 * separated from the figure by space rather than by a rule, with the warning
 * colour spent only where something is actually wrong. The figure is now
 * `text-figure` against this block's `text-2xs`, which is the hierarchy that
 * was missing.
 */
function Notes({ figure }: { figure: Figure }) {
  const rows: { key: string; term: string; value: React.ReactNode }[] = []

  if (figure.kind === 'score') {
    // One sentence, with the link inside it. A score whose page cannot be
    // opened is a number nobody can check, and the link's accessible name is
    // the URL itself so "which page?" is answered without following it.
    rows.push({
      key: 'read',
      term: 'Source',
      value: (
        <>
          Measured {figure.measured_at} from{' '}
          <a
            href={figure.source_url}
            target="_blank"
            rel="noreferrer noopener"
            className="break-all underline decoration-ink-300 underline-offset-2 hover:text-ink-900"
          >
            {figure.source_url}
          </a>
        </>
      ),
    })
  }

  if (figure.kind === 'amount') {
    // ADR 0038. "Read from your CRM" about somebody's own typing is the
    // specific thing this tile could get wrong, and the two populations look
    // identical once totalled.
    rows.push({
      key: 'source',
      term: 'Source',
      value: figure.self_reported
        ? `Counted from what you recorded, last updated ${figure.measured_at}`
        : `Read ${figure.measured_at} from your ${figure.source}`,
    })
  }

  if (figure.kind === 'count') {
    rows.push({
      key: 'source',
      term: 'Source',
      value: `Counted from what your workspace recorded, last updated ${figure.recorded_at}`,
    })
    rows.push({
      key: 'complete',
      term: 'Completeness',
      value: figure.complete_as_of
        ? `You confirmed this is all of them, as of ${figure.complete_as_of}.`
        : 'You have not said whether this is all of them, so this counts the record rather than the company.',
    })
  }

  if (figure.kind === 'rate') {
    rows.push({
      key: 'source',
      term: 'Source',
      value: `Counted from what your workspace recorded, last updated ${figure.recorded_at}`,
    })
    if (figure.grace_days !== null) {
      // The rule the figure was computed under. A percentage whose rule is
      // invisible cannot be checked by the person it is about.
      rows.push({
        key: 'rule',
        term: 'The rule',
        value: `Late means more than ${figure.grace_days} ${figure.grace_days === 1 ? 'day' : 'days'} past the date you promised.`,
      })
    }
    if (figure.excluded > 0) {
      rows.push({
        key: 'excluded',
        term: 'Left out',
        value: `${figure.excluded} ${figure.excluded === 1 ? 'is' : 'are'} recorded with no figure, so ${figure.excluded === 1 ? 'it is' : 'they are'} not in this share.`,
      })
    }
  }

  if (figure.kind === 'count' && figure.undated > 0) {
    // Said plainly rather than folded into "on track". Nobody named a day, so
    // nothing is late — and a reader weighing the overdue count needs to know
    // how many could never have been counted in it.
    rows.push({
      key: 'undated',
      term: 'No due date',
      value: `${figure.undated} ${figure.undated === 1 ? 'has' : 'have'} no due date, so ${figure.undated === 1 ? 'it is' : 'they are'} never counted as late.`,
    })
  }

  if (rows.length === 0) return null

  return (
    <div className="flex flex-col gap-1 text-2xs leading-relaxed text-ink-400">
      {rows.map((row) => (
        <p key={row.key} className="max-w-read">
          {row.value}
        </p>
      ))}
    </div>
  )
}

/**
 * The arithmetic.
 *
 * A scored audit's working is its checks — every one the calculator ran, in its
 * order, with the points it contributed and the evidence it saw. Failures are
 * not styled as errors: a page without structured data has not done anything
 * wrong, and colouring nine rows red would turn an observation into a reprimand.
 *
 * An amount figure has no checks — a pipeline is a sum of rows, not nine
 * weighted observations — and inventing a checklist to fill the space would be
 * the drawer showing working that never happened. It gets the counts it was
 * built from, which is the whole of its arithmetic.
 */
function Arithmetic({ figure }: { figure: Figure }) {
  if (figure.kind === 'amount') {
    return (
      <Line
        head={`${figure.count} counted, ${figure.count - figure.uncounted} added`}
        body={
          figure.uncounted > 0
            ? `${figure.uncounted} ${figure.uncounted_label}, so counted and not added.`
            : `Every one of them is priced, so all ${figure.count} are in the total.`
        }
      />
    )
  }

  if (figure.kind === 'count') {
    // A census has no checks either. Its whole arithmetic is the partition —
    // done plus open, and open split into late, undated and still to come.
    return (
      <Line
        head={`${figure.recorded} recorded, ${figure.recorded - figure.open_items} done, ${figure.open_items} open`}
        body={`Of the ${figure.open_items} open, ${figure.overdue} past a date and ${figure.undated} with no date.`}
      />
    )
  }

  if (figure.kind === 'score') {
    return (
      <ul className="divide-y divide-ink-100">
        {figure.checks.map((check) => (
          <li key={check.id} className="flex flex-wrap gap-x-3 gap-y-1 py-2">
            <span
              className={`tnum shrink-0 text-2xs uppercase tracking-[0.08em] ${
                check.passed ? 'text-steel-600' : 'text-ink-400'
              }`}
            >
              {check.passed ? `+${check.weight}` : `0 / ${check.weight}`}
            </span>
            <span className="min-w-0 grow">
              <span className="text-meta text-ink-800">{check.label}</span>
              {/* The calculator's own words. An observation, never advice. */}
              <span className="mt-0.5 block text-meta text-ink-500">{check.evidence}</span>
            </span>
          </li>
        ))}
      </ul>
    )
  }

  return null
}

function Line({ head, body }: { head: string; body: string }) {
  return (
    <p className="py-1 text-meta">
      <span className="tnum text-ink-800">{head}</span>
      <span className="mt-0.5 block text-ink-500">{body}</span>
    </p>
  )
}

/**
 * The whole drawer, in one order on every tile.
 *
 * The order is the point. A reader who learns that "Why this number" opens
 * *measures, provenance, arithmetic, identifiers* on the SEO tile knows where
 * to look on the stock tile without reading it. Twelve tiles that each arranged
 * the same five things differently is what the face of the card used to be.
 */
function Working({
  block,
  narration,
  figure,
}: {
  block: DirectorBlock
  narration: Narration | null
  figure: Figure
}) {
  const [open, setOpen] = useState(false)

  return (
    <Disclosure
      summary={`${open ? '−' : '+'} why this number`}
      open={open}
      onOpenChange={setOpen}
      className="mt-auto border-t border-ink-100 pt-3"
    >
      <div className="flex flex-col gap-3 rounded-data bg-bone-50 px-4 py-3.5">
        <Arithmetic figure={figure} />

        {/* The identifiers. Moved here from the face of the card: they exist so
            a tile on a screen can be traced back to the paragraph that specified
            it, which is a need of somebody debugging the product rather than of
            somebody running a business — and that person is already in here. */}
        <div className="flex flex-wrap items-center gap-2 border-t border-ink-100 pt-3 text-2xs text-ink-400">
          <span className="font-mono">{figure.method}</span>
          {/* Which `SKILL.md` wrote the sentence above, beside the arithmetic
              that produced the number. A disputed sentence should trace back to
              its instructions as readily as a disputed figure traces back to its
              working. */}
          {narration ? (
            <span className="font-mono">narrate-metric {narration.prompt_version}</span>
          ) : null}
        </div>
      </div>
    </Disclosure>
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
  // field only a scored figure has.
  if (figure.kind !== 'score') return null

  // Read out here, not inside `explain`. TypeScript does not carry the narrowing
  // above into a hoisted function declaration, so the closure took `Figure` and
  // lost the field.
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

  const label = WORTH_RETRYING.has(reason)
    ? 'Try again'
    : narration
      ? 'Explain again'
      : 'Explain this score'

  return (
    <div className="flex flex-col gap-2">
      {narration ? (
        <p className="max-w-read text-body leading-relaxed text-ink-700">{narration.prose}</p>
      ) : null}

      {superseded ? (
        <p className="field-hint">This score has changed since the page loaded. Reload to see it.</p>
      ) : message ? (
        <p className="field-hint">{message}</p>
      ) : null}

      {NOTHING_TO_RETRY.has(reason) ? null : (
        <Button
          size="sm"
          // Quiet once there is a sentence. Re-narrating spends tokens, so it
          // must not be the dominant control on the tile.
          variant={narration ? 'quiet' : 'secondary'}
          onClick={explain}
          loading={busy}
          loadingLabel="Writing…"
          className="self-start"
        >
          {label}
        </Button>
      )}
    </div>
  )
}

/**
 * What to do about the state, when there is something to do.
 *
 * Unchanged in wording. The `live` and `planned` cases return nothing, which is
 * what makes the remaining six read as instructions rather than as a status
 * line every tile happens to carry.
 */
function Consequence({ block }: { block: DirectorBlock }) {
  switch (block.state) {
    case 'locked':
    case 'partial':
      // Doc 04 §6 rule 1: the tile is a call to action, not a failure. The
      // sentence comes from the API so one wording change reaches every
      // surface, and so a tile cannot ship with the outline drawn and the
      // sentence forgotten.
      return block.unlock ? <p className="note-warn font-medium">{block.unlock}</p> : null

    case 'warming':
      return (
        <p className="field-hint">
          Connected. Not enough history to compare against yet — nothing to do but wait.
        </p>
      )

    case 'stale':
      return (
        <p className="note-warn font-medium">
          This figure is real and out of date. Its age is shown with it, because a
          number from last quarter reads as current unless it says otherwise.
        </p>
      )

    case 'unavailable':
      return (
        <p className="note-warn font-medium">
          We could not compute this. The reason is recorded against the attempt rather
          than guessed at here.
        </p>
      )

    case 'self_reported':
      return (
        <p className="field-hint">
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

/**
 * Which capability this tile is, and which paragraph specified it.
 *
 * Kept on the face rather than moved into the working, for two reasons the
 * audit's "specification ids are debug metadata" note did not account for. A
 * tile in the `planned` state has no figure and therefore no drawer, so the
 * drawer is not a place these can always live. And traceability from a tile on
 * a screen to the capability id is a property the product asserts, not an
 * implementation detail — it is how a disputed number is reported.
 *
 * What changed is the weight. This was a bordered row of a tracked-out
 * reference, a monospace key and an outlined pill, at the same size as the
 * figure's qualifier. It is now the smallest step in the scale in the quietest
 * foreground the palette has, and the kind is plain text rather than a second
 * badge competing with the state marker.
 */
function Identifiers({ block }: { block: DirectorBlock }) {
  return (
    <p className="mt-auto flex flex-wrap items-center gap-x-2 gap-y-1 pt-1 text-2xs text-ink-300">
      {/* Absent for the thirteen capabilities doc 08 specified and doc 05 never
          did. An empty reference would be a label pointing at no paragraph. */}
      {block.doc05_id ? <span className="tracking-[0.1em]">{block.doc05_id}</span> : null}
      <span className="font-mono tracking-[0.04em]">{block.key}</span>
      <span>{block.block}</span>
    </p>
  )
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

  // Both conditions, not either. A state in `hasFigure` with no figure is a
  // serving bug and must not render a drawer onto nothing; a figure arriving in
  // a state the machine says should not carry one is a number we were told we
  // should not have. Requiring both means neither is papered over.
  const figure = hasFigure(block.state) && block.figure ? block.figure : null

  return (
    <li
      className={`flex flex-col gap-3 rounded-data border px-5 py-5 shadow-e1 transition-[border-color,box-shadow] duration-base ease-out hover:shadow-e2 ${
        dimmed ? 'border-ink-100 bg-bone-50' : 'border-ink-100 bg-white'
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-card font-medium text-ink-900">{block.name}</h3>
          <p className="mt-0.5 text-meta leading-snug text-ink-500">{block.shows}</p>
        </div>
        {/* Nothing at all when the state is `live`. See `STATE_TONE`. */}
        <StateDot tone={STATE_TONE[block.state]} label={STATE_LABEL[block.state]} />
      </div>

      {figure ? (
        <>
          <Head figure={figure} />
          <Breakdown figure={figure} />
          <Caveat figure={figure} />
          {/* What was counted and what was not. The guard against a real number
              under a headline that promises more than it measured — the one
              dishonest thing this tile could ship. */}
          <Measures figure={figure} />
          <Notes figure={figure} />
          {/* Between the figure and the consequence: a gloss on the number
              belongs on the number's side of that line. **Scored figures only**
              (ADR 0033) — `narrate-metric` speaks in numerator and denominator,
              so a pipeline sentence grounded in those keys would be grounded in
              nothing, and the API refuses the capability with a 404. */}
          {figure.kind === 'score' ? (
            <Explanation
              block={block}
              department={department}
              narration={narration}
              onNarration={setNarration}
            />
          ) : null}
          <Consequence block={block} />
          <div className="flex flex-wrap items-center gap-1.5">
            <Vouched figure={figure} />
          </div>
          <Working block={block} narration={narration} figure={figure} />
        </>
      ) : (
        <>
          <p className="text-meta leading-relaxed text-ink-400">{KIND_PROMISE[block.block]}</p>
          <Consequence block={block} />
        </>
      )}

      <Identifiers block={block} />
    </li>
  )
}
