import { STATE_LABEL, type BlockKind, type DirectorBlock, type WidgetState } from '@/lib/dashboard-client'

/**
 * One capability on the rail, in whatever state it is actually in.
 *
 * `doc/13` §7. Eight states, and **each one has to tell the reader something
 * different to do** — two states that produce the same action should be one
 * state, and a state whose action is wrong is worse than no tile at all. That
 * is the rule this component exists to hold, and the reason the copy lives here
 * rather than in nine block components that would each drift.
 *
 * ## Why there is no value slot yet
 *
 * The API's block carries a name, what it will show, its state and its unlock —
 * and **no number**. Nothing computes one yet: `calculators/deltas.py` is
 * written and uncalled, and no route serves a narrated figure. So a value area
 * here would be an outline, and `dashboards.py` is explicit that a widget
 * outline on a screen is the thing a screenshot cannot distinguish from a
 * working one.
 *
 * What the block *kind* changes today is therefore the sentence about what it
 * will draw, not a fake rendering of it. The kinds get their data shapes when
 * the first tile is computed — the same discipline as `connected_sources()`
 * returning an empty set rather than a guess.
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
 */
function hasFigure(state: WidgetState): boolean {
  return state === 'live' || state === 'partial' || state === 'stale'
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

      <Consequence block={block} />

      {/* The working drawer's place, and it is reserved rather than drawn. It
          opens onto the `generation` row behind the figure — method, inputs,
          arithmetic, window — and there is no row to open until something is
          computed. A disabled control that says why beats a control that is
          absent for reasons the reader has to guess. */}
      {hasFigure(block.state) ? (
        <button
          type="button"
          disabled
          className="mt-4 self-start rounded-lg border border-ink-200 px-3 py-1.5 text-sm text-ink-500"
        >
          + why this number
        </button>
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
