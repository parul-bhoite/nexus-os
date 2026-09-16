'use client'

import type { Coverage as Bands } from '@/lib/dashboard-client'

/**
 * Where the product is, for this company — ADR 0030.
 *
 * This replaces the "Company Health 82/100" the reference mock opened with. A
 * composite over two measured capabilities out of eighty-nine would read as a
 * verdict on the business and is a verdict on one web page, so the region says
 * something narrower and true instead: **who has to move next.**
 *
 * ## Why a bar is honest here and would not have been over sources
 *
 * The three bands partition what a caller can reach, so every capability is in
 * exactly one. Banding by *connected source* would not partition anything —
 * `marketing.seo_gaps` computes today and is still missing `dataforseo`, so it
 * belongs in two bands at once and a stacked bar would assert it belongs in one.
 *
 * ## The third band is the honest headline
 *
 * "Not built yet" is ours, and naming it is what makes the other two mean
 * anything: without it, a founder reads two-of-eighty-nine as a product waiting
 * on them. `planned` tiles already say this one at a time; this says it once, at
 * the top.
 */

/** A band, as a row rather than a chart label — the number is the point and the
 *  sentence beside it is what stops the number being misread. */
function Band({
  count,
  label,
  swatch,
  children,
}: {
  count: number
  label: string
  swatch: string
  children: React.ReactNode
}) {
  return (
    <li className="flex gap-4 border-b border-ink-100 py-3 last:border-b-0">
      <span aria-hidden className={`mt-2 h-2 w-2 shrink-0 rounded-sm ${swatch}`} />
      <div className="min-w-0">
        <p className="text-[0.95rem] text-ink-900">
          <span className="font-display text-lg font-semibold tabular-nums">{count}</span>{' '}
          <span className="font-medium">— {label}</span>
        </p>
        <p className="mt-0.5 max-w-prose text-sm leading-relaxed text-ink-600">{children}</p>
      </div>
    </li>
  )
}

export function Coverage({ bands }: { bands: Bands }) {
  // Guarded rather than assumed. The API cannot serve a total of zero for a
  // caller who holds a department, but a division by it would render `NaN%`
  // across the bar — and a meter showing nothing is indistinguishable from a
  // meter showing a real zero.
  const width = (count: number) => (bands.total > 0 ? `${(count / bands.total) * 100}%` : '0%')

  return (
    <section aria-labelledby="coverage-heading">
      <h2 id="coverage-heading" className="font-display text-title font-medium text-ink-900">
        Where the product is, for you
      </h2>
      <p className="mt-1 max-w-prose text-sm text-ink-500">
        {bands.total} capabilities, split by what stands in front of each one.
      </p>

      <div className="mt-4 rounded-2xl border border-ink-100 bg-white px-5 py-5 shadow-paper">
        <div
          role="img"
          aria-label={`${bands.measuring} measuring, ${bands.reading_back} reading your answers back, ${bands.not_built} not built yet, of ${bands.total}`}
          className="flex h-1.5 overflow-hidden rounded-full bg-bone-200"
        >
          <span className="bg-steel-500" style={{ width: width(bands.measuring) }} />
          <span className="bg-gold-400" style={{ width: width(bands.reading_back) }} />
        </div>

        <ul className="mt-4">
          <Band count={bands.measuring} label="producing a figure" swatch="bg-steel-500">
            Computed from what we could measure, each with its denominator and its
            working.
          </Band>
          <Band count={bands.reading_back} label="reading your answers back" swatch="bg-gold-400">
            Your own words rather than a measurement — which is why they never render as
            a score.
          </Band>
          <Band count={bands.not_built} label="not built yet" swatch="bg-bone-300">
            Ours to fix, not yours. No calculator exists for these, so no connection you
            make would switch one on.
          </Band>
        </ul>

        <p className="mt-4 max-w-prose border-t border-ink-100 pt-3 text-sm leading-relaxed text-ink-600">
          <span className="font-semibold text-ink-800">There is no company score.</span>{' '}
          Averaging what we hold would produce something that looks like a verdict on the
          business and is a verdict on one web page. It appears when there is enough
          behind it to mean what it would appear to mean.
        </p>
      </div>
    </section>
  )
}
