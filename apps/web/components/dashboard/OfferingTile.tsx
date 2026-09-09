import { STATE_LABEL, type Offering, type WidgetState } from '@/lib/dashboard-client'

/**
 * One widget's tile, in whatever state it is actually in.
 *
 * Doc 04 §6 rule 1: *"Every locked tile states its unlock. Not a spinner, not a
 * zero. The tile is a call to action, not a failure."* So the tile always
 * carries three things — what it will show, what state it is in, and what it
 * needs — and it never carries a figure, because I10 makes a `0` on a screen a
 * statement about the business rather than about the data.
 *
 * `planned` and `locked` look different on purpose. A locked tile is an
 * invitation to connect something; a planned one is an admission that the
 * widget does not exist yet, and dressing it as locked would be a promise the
 * product cannot keep.
 */

const STATE_STYLES: Record<WidgetState, string> = {
  live: 'bg-steel-100 text-steel-700',
  partial: 'bg-gold-200 text-clay-600',
  locked: 'bg-clay-100 text-clay-600',
  warming: 'bg-gold-100 text-clay-600',
  self_reported: 'bg-bone-200 text-ink-600',
  // Added when the API's two remaining states reached this client. `tsc` found
  // the gap: `STATE_LABEL` would have produced `undefined` for either of them,
  // so a stale figure would have rendered with a blank chip beside it — a
  // number that looks current with nothing saying it is not.
  stale: 'bg-clay-100 text-clay-600',
  unavailable: 'bg-bone-200 text-ink-500',
  planned: 'bg-bone-200 text-ink-500',
}

export function OfferingTile({ offering }: { offering: Offering }) {
  const dimmed = offering.state === 'planned'

  return (
    <li
      className={`flex flex-col rounded-2xl border px-5 py-5 shadow-paper transition-colors ${
        dimmed ? 'border-ink-100 bg-bone-50' : 'border-ink-100 bg-white'
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <h3 className="font-display text-lg leading-snug text-ink-900">{offering.name}</h3>
        <span
          className={`shrink-0 rounded-full px-2.5 py-1 font-mono text-2xs uppercase tracking-[0.08em] ${STATE_STYLES[offering.state]}`}
        >
          {STATE_LABEL[offering.state]}
        </span>
      </div>

      <p className="mt-2 text-[0.95rem] leading-relaxed text-ink-600">{offering.shows}</p>

      {offering.unlock ? (
        <p className="mt-3 text-sm font-medium text-clay-600">{offering.unlock}</p>
      ) : null}

      {offering.note ? (
        <p className="mt-2 text-sm leading-relaxed text-ink-500">{offering.note}</p>
      ) : null}

      <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-ink-100 pt-3">
        <span className="font-mono text-2xs uppercase tracking-[0.1em] text-ink-400">
          {offering.id}
        </span>
        {offering.phase > 1 ? (
          <span className="rounded-full border border-ink-200 px-2 py-0.5 font-mono text-2xs uppercase tracking-[0.08em] text-ink-500">
            Phase {offering.phase}
          </span>
        ) : null}
      </div>
    </li>
  )
}
