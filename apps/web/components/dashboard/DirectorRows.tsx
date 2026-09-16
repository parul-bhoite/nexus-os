'use client'

import Link from 'next/link'
import type { DirectorRow } from '@/lib/dashboard-client'

/**
 * The seven directors, as a block rather than the navigation.
 *
 * `doc/14` step 6. This is the department tab rail, demoted: it used to sit at
 * the top of a page and gate it, so a founder chose a department before the
 * product said anything. Here it is something they read past, and the left panel
 * is how they actually move around.
 *
 * **Composed, never greyed** — the same rule the panel follows. A department the
 * caller cannot open is absent from the payload, so the grid simply has fewer
 * cells. Drawing seven and dimming six would advertise what somebody cannot
 * have, on every page load, permanently.
 *
 * Every sentence is the server's. Four states each say something different
 * (`domain/director_rows.py`), and the difference is the whole point: telling
 * somebody to answer questions for a department whose questions are all answered
 * sends them looking for a form that is not there.
 */

const CHIP: Record<DirectorRow['state'], string> = {
  measuring: 'bg-steel-100 text-steel-700',
  answerable: 'bg-clay-100 text-clay-600',
  waiting: 'bg-gold-100 text-clay-600',
  empty: 'bg-bone-200 text-ink-500',
}

const CHIP_LABEL: Record<DirectorRow['state'], string> = {
  measuring: 'Measuring',
  answerable: 'Answerable now',
  waiting: 'Waiting',
  empty: 'Nothing yet',
}

export function DirectorRows({ rows }: { rows: DirectorRow[] }) {
  if (rows.length === 0) return null

  return (
    <section aria-labelledby="directors-heading">
      <h2 id="directors-heading" className="font-display text-title font-medium text-ink-900">
        {rows.length === 1 ? 'Your director' : `The ${rows.length} directors`}
      </h2>
      <p className="mt-1 max-w-prose text-sm text-ink-500">
        A summary, not a menu — the panel on the left is how you open one.
      </p>

      <ul className="mt-4 grid gap-px overflow-hidden rounded-2xl border border-ink-100 bg-ink-100 sm:grid-cols-2 lg:grid-cols-3">
        {rows.map((row) => (
          <li key={row.department} className="flex flex-col gap-2 bg-white px-4 py-4">
            <div className="flex items-start justify-between gap-3">
              <h3 className="text-[0.95rem] font-semibold text-ink-900">{row.label}</h3>
              <span
                className={`shrink-0 rounded-full px-2.5 py-1 font-mono text-2xs uppercase tracking-[0.08em] ${
                  CHIP[row.state]
                }`}
              >
                {CHIP_LABEL[row.state]}
              </span>
            </div>
            {/* The server's sentence. A state-to-copy map in the browser is the
                failure `unlock` already avoids — one wording change would have
                to be made in as many places as there are clients. */}
            <p className="text-sm leading-relaxed text-ink-600">{row.line}</p>
            <Link
              href={row.path}
              className="mt-auto pt-1 text-sm font-medium text-steel-600 hover:text-steel-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-steel-500"
            >
              Open {row.label} →
            </Link>
          </li>
        ))}
      </ul>
    </section>
  )
}
