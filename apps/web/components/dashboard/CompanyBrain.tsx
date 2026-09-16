'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'
import { fetchBrain, type Brain } from '@/lib/settings-client'

/**
 * What NEXUS is working from — `doc/14` step 7.
 *
 * The founder's own words, read back. **This panel carries no number**, and the
 * absence is the point: doc 05 §0 requires that something somebody typed and
 * something we measured never look alike, so the one region built entirely out
 * of stated facts is also the one with no figure in it.
 *
 * ## Fetched separately, and quietly
 *
 * `GET /brain` already exists and Settings already reads it. Folding it into
 * `/dashboards/surface` would put a second query on the critical path of the
 * page's first paint for content that sits well below the fold. So this loads on
 * its own and **renders nothing at all while it does** — no skeleton, because a
 * placeholder in the shape of a brain is indistinguishable from a brain that
 * came back empty.
 *
 * A failure is a quiet line rather than silence, for the reason every other
 * region on this surface gives: *could not load* and *nothing here yet* are
 * different facts, and swallowing the first makes it wear the second's clothes.
 * It is deliberately not an error box — the surface above has already loaded
 * and is useful, and a failure to draw a secondary panel must not cover it.
 *
 * ## The assumptions block is the part that matters
 *
 * A brain a founder cannot audit is a brain they have to take on trust, and this
 * product's whole claim is that they never have to. What NEXUS *assumed* is
 * therefore not a footnote — it is the one part of this panel somebody is
 * expected to act on.
 */

const FIELDS: { key: keyof Brain; label: string }[] = [
  { key: 'profile', label: 'What the company does' },
  { key: 'products_services', label: 'Products and services' },
  { key: 'target_customers', label: 'Who buys from you' },
  { key: 'goals', label: 'Goals' },
]

type State =
  | { status: 'loading' }
  | { status: 'ready'; brain: Brain }
  | { status: 'unreachable' }

export function CompanyBrain() {
  const [state, setState] = useState<State>({ status: 'loading' })

  useEffect(() => {
    let live = true
    fetchBrain()
      .then((brain) => {
        if (live) setState({ status: 'ready', brain })
      })
      .catch(() => {
        if (live) setState({ status: 'unreachable' })
      })
    return () => {
      live = false
    }
  }, [])

  if (state.status === 'loading') return null

  if (state.status === 'unreachable') {
    return (
      <section aria-labelledby="brain-heading">
        <h2 id="brain-heading" className="font-display text-title font-medium text-ink-900">
          Company Brain
        </h2>
        <p className="mt-2 max-w-prose text-sm text-ink-500">
          Could not load what NEXUS is working from. Nothing above is affected — this
          panel reads from a separate place, and it is the reading that failed rather
          than the brain.
        </p>
      </section>
    )
  }

  const brain = state.brain

  const answered = FIELDS.filter((field) => brain[field.key])

  return (
    <section aria-labelledby="brain-heading">
      <h2 id="brain-heading" className="font-display text-title font-medium text-ink-900">
        Company Brain
      </h2>
      <p className="mt-1 max-w-prose text-sm text-ink-500">
        Everything NEXUS is working from. Your words, not a measurement — which is why
        nothing here is a score.
      </p>

      <div className="mt-4 rounded-2xl border border-ink-100 bg-bone-100 px-5 py-5">
        {answered.length > 0 ? (
          <dl className="grid gap-x-8 sm:grid-cols-2">
            {answered.map((field) => (
              <div key={field.key} className="border-b border-ink-200 py-3">
                <dt className="font-mono text-2xs uppercase tracking-[0.07em] text-ink-500">
                  {field.label}
                </dt>
                <dd className="mt-1 text-sm leading-relaxed text-ink-800">
                  {brain[field.key] as string}
                </dd>
              </div>
            ))}
          </dl>
        ) : (
          <p className="max-w-prose text-sm leading-relaxed text-ink-600">
            {/* Not "no data". Nothing has been built yet is a different fact from
                nothing being known, and setup is where one becomes the other. */}
            Nothing has been assembled yet. It is built from your setup answers, so it
            fills in as you answer them.
          </p>
        )}

        {brain.assumptions.length > 0 ? (
          <div className="mt-4 rounded-lg border-l-[3px] border-clay-500 bg-clay-100 px-4 py-3">
            <p className="font-mono text-2xs uppercase tracking-[0.07em] text-clay-600">
              Assumptions we are working from
            </p>
            <ul className="mt-2 flex flex-col gap-1">
              {brain.assumptions.map((assumption) => (
                <li key={assumption} className="text-sm leading-relaxed text-ink-800">
                  {assumption}
                </li>
              ))}
            </ul>
            <p className="mt-2 text-sm text-ink-600">
              These came from your website and your answers, not from you directly.
              Correcting one changes what the capabilities that read it will count.
            </p>
          </div>
        ) : null}

        <Link
          href="/settings"
          className="mt-4 inline-block text-sm font-medium text-steel-600 underline decoration-steel-300 underline-offset-2 hover:text-steel-700"
        >
          Edit in settings
        </Link>
      </div>
    </section>
  )
}
