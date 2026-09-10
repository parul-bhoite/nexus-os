'use client'

import { useState } from 'react'
import {
  STATE_LABEL,
  type BlockKind,
  type DirectorBlock,
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

/** The score, its denominator, and how many checks stand behind it. */
function Figure({ block }: { block: DirectorBlock }) {
  const figure = block.figure
  if (!figure) return null

  return (
    <div className="mt-4">
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
function Working({ block }: { block: DirectorBlock }) {
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
          <ul className="divide-y divide-ink-100">
            {figure.checks.map((check) => (
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
          </p>
        </div>
      ) : null}
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

export function BlockCard({ block }: { block: DirectorBlock }) {
  const dimmed = block.state === 'planned'

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

      <Consequence block={block} />

      {/* Both conditions, not either. A state in `hasFigure` with no figure is
          a serving bug and must not render a drawer onto nothing; a figure
          arriving in a state the machine says should not carry one is a number
          we were told we should not have. Requiring both means neither is
          papered over. */}
      {hasFigure(block.state) && block.figure ? (
        <Working block={block} />
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
