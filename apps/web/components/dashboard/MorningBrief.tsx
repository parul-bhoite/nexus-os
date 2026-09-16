'use client'

import type { Brief, BriefItem } from '@/lib/dashboard-client'

/**
 * The first region of the common surface: what was found, ranked by what it cost.
 *
 * ADR 0029, and almost all of the thinking is already server-side. The ranking,
 * the three states and every sentence are decided in `domain/brief.py`, so this
 * file draws and does not judge — a browser that re-sorted, re-worded or
 * re-grouped would be a second opinion about the same data, and the two would
 * drift.
 *
 * **Every state renders something.** The region is never hidden, because a brief
 * that disappeared would let an audit that never ran look like an audit that
 * found nothing (I10). `not_measured` is a different sentence from `all_held`,
 * not a quieter version of it.
 *
 * ## Two tiers, because the data has two
 *
 * Prosoft's eight failures are two at ten points and six at five. A "top three"
 * would cut through the six-way tie arbitrarily, so the cut follows the weights:
 * the heaviest band gets full items, and everything tied below collapses into a
 * chip row that still names each observation. That keeps the whole list on
 * screen without pretending eight things need equal attention.
 */

/** Points lost is the hierarchy. No severity words — the number is computed and
 *  a label like "critical" would not be. */
function Cost({ points, quiet = false }: { points: number; quiet?: boolean }) {
  return (
    <span
      className={`shrink-0 whitespace-nowrap rounded px-2 py-0.5 font-mono text-2xs uppercase tracking-[0.06em] ${
        quiet ? 'bg-bone-200 text-ink-500' : 'bg-clay-100 text-clay-600'
      }`}
    >
      {points} {points === 1 ? 'point' : 'points'}
    </span>
  )
}

function Finding({ item }: { item: BriefItem }) {
  return (
    <li className="flex gap-4 border-b border-ink-100 py-4 last:border-b-0">
      <span
        aria-hidden
        className={`mt-1.5 w-1 shrink-0 rounded-full ${
          item.kind === 'unmeasured' ? 'bg-ink-300' : 'bg-clay-500'
        }`}
      />
      <div className="min-w-0 grow">
        <h4 className="flex items-baseline justify-between gap-4 text-[0.95rem] font-semibold text-ink-900">
          <span>{item.headline}</span>
          {item.cost > 0 ? <Cost points={item.cost} /> : null}
        </h4>
        <p className="mt-1 max-w-prose text-sm leading-relaxed text-ink-600">{item.detail}</p>
        {/* Provenance, in the machine face. No `generation` row backs a brief —
            nothing was generated — so the check id and the calculator are the
            whole audit trail, and they are enough to reproduce the weight. */}
        <p className="mt-1.5 font-mono text-2xs text-ink-400">
          {[item.check_id, item.method].filter(Boolean).join(' · ') || item.capability_id}
        </p>
      </div>
    </li>
  )
}

export function MorningBrief({ brief }: { brief: Brief }) {
  const failures = brief.items.filter((item) => item.kind === 'check_failed')
  const heaviest = failures.length > 0 ? failures[0].cost : 0
  const lead = brief.items.filter((item) => item.kind === 'unmeasured' || item.cost === heaviest)
  const tail = failures.filter((item) => item.cost < heaviest)

  return (
    <section aria-labelledby="brief-heading">
      <h2 id="brief-heading" className="font-display text-title font-medium text-ink-900">
        Morning brief
      </h2>
      <p className="mt-1 max-w-prose text-sm text-ink-500">
        {/* Found, never changed. Nothing re-crawls yet, so a heading with a
            date range would claim a comparison nobody made. */}
        What was found, ranked by what it cost.
      </p>

      <div className="mt-4 rounded-2xl border border-ink-100 bg-white px-5 py-5 shadow-paper">
        {brief.state === 'findings' ? (
          <>
            <div className="flex flex-wrap items-baseline justify-between gap-3 border-b border-ink-100 pb-3">
              <h3 className="font-display text-lg text-ink-900">
                {brief.checks_total - brief.checks_passed} of {brief.checks_total} checks did not
                hold
              </h3>
              <span className="font-mono text-2xs tracking-[0.05em] text-ink-500">
                {brief.points_total - brief.points_held} of {brief.points_total} points not held
              </span>
            </div>

            <ul>
              {lead.map((item) => (
                <Finding key={item.check_id || item.capability_id} item={item} />
              ))}
            </ul>

            {tail.length > 0 ? (
              <div className="border-t border-ink-100 pt-4">
                <h4 className="flex items-baseline justify-between gap-4 text-sm font-semibold text-ink-900">
                  <span>
                    {tail.length} more {tail.length === 1 ? 'check' : 'checks'} did not hold
                  </span>
                  <Cost points={tail[0].cost} quiet />
                </h4>
                {/* Both halves, always. The first cut of this row showed only
                    the evidence, and "137 characters" or "0/37 images" tells a
                    reader nothing about what was being counted — the check's
                    label is the half that identifies it. */}
                <ul className="mt-2 flex flex-col gap-1.5 sm:flex-row sm:flex-wrap">
                  {tail.map((item) => (
                    <li
                      key={item.check_id}
                      className="rounded border border-ink-200 px-2 py-1 text-2xs text-ink-600"
                    >
                      {item.headline}{' '}
                      <span className="font-mono text-ink-400">{item.detail}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            <p className="mt-4 border-t border-ink-100 pt-3 max-w-prose text-sm text-ink-500">
              <span className="font-semibold text-ink-800">
                {brief.checks_passed} checks passed
              </span>
              , holding {brief.points_held} points.
            </p>
          </>
        ) : (
          <>
            <div className="flex flex-wrap items-baseline justify-between gap-3 border-b border-ink-100 pb-3">
              <h3 className="font-display text-lg text-ink-900">
                {brief.state === 'all_held'
                  ? `All ${brief.checks_total} checks held`
                  : 'Nothing measured yet'}
              </h3>
              {brief.state === 'all_held' ? (
                <span className="font-mono text-2xs tracking-[0.05em] text-ink-500">
                  {brief.points_held} of {brief.points_total} points held
                </span>
              ) : null}
            </div>
            {/* The server's words. A reason-to-sentence map here is the failure
                `unlock` already avoids: one wording change would have to be
                made in as many places as there are clients. */}
            <p className="mt-4 max-w-prose text-[0.95rem] leading-relaxed text-ink-700">
              {brief.message}
            </p>
          </>
        )}
      </div>
    </section>
  )
}
