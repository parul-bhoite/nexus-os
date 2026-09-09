'use client'

import { useEffect, useState } from 'react'
import { AuthError } from '@/lib/auth-client'
import {
  fetchSetup,
  type DirectorSetup,
  type NotAsked,
  type SetupFact,
  type WatchItem,
} from '@/lib/dashboard-client'
import { Waiting } from '@/components/ui/Waiting'

/**
 * The Setup and Watchlist tabs. `doc/13` §4 and §9.
 *
 * These are the only two tabs on a day-one dashboard with anything on them, and
 * that is the whole argument for building them before the first connector. With
 * no CRM and no accounting system the rest of the rail is honest and empty; this
 * is the founder's own answers, read back.
 *
 * ## Three things it does that a form never does
 *
 * **It names who reads each answer.** Q33's rule is that a question with no
 * consumer is a form field, not a question. Showing the consumer is that rule
 * turned outward: the founder can see what their answer is *for*, and can see
 * when the honest answer is "nothing yet".
 *
 * **It carries the date.** An answer from four months ago and one from
 * yesterday warrant different confidence, and nothing else on the page can tell
 * a reader which they are looking at.
 *
 * **It never styles an answer as a measurement.** `doc/05` §0: a number they
 * typed and a number we measured must never look identical, because the second
 * can contradict them and the first cannot. So an answer is quoted, with an
 * attribution — never set in a metric slot with a delta beside it. That is what
 * the `facts` block kind exists for, and this is the first thing to use it.
 */

function when(iso: string): string {
  if (!iso) return ''
  const parsed = new Date(iso)
  return Number.isNaN(parsed.getTime()) ? '' : parsed.toLocaleDateString()
}

function Fact({ fact }: { fact: SetupFact }) {
  const said = when(fact.answered_at)

  return (
    <li className="border-t border-ink-100 py-4 first:border-t-0 first:pt-0">
      <p className="text-sm text-ink-500">{fact.question}</p>
      {/* Quoted, not tabulated. The quotation marks are the treatment: they say
          this is somebody's sentence rather than a figure we stand behind. */}
      <blockquote className="mt-1.5 text-[1.05rem] leading-relaxed text-ink-900">
        &ldquo;{fact.answer}&rdquo;
      </blockquote>
      <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-ink-400">
        {said ? <span>You, {said}</span> : <span>You</span>}
        <span className="font-mono text-2xs tracking-[0.04em]">reads it: {fact.reads_it}</span>
      </p>
    </li>
  )
}

function Watch({ item }: { item: WatchItem }) {
  const said = when(item.answered_at)

  return (
    <li className="flex flex-col rounded-2xl border border-ink-100 bg-white px-5 py-5 shadow-paper">
      <h3 className="font-display text-lg leading-snug text-ink-900">{item.label}</h3>

      <blockquote className="mt-2 text-[0.95rem] leading-relaxed text-ink-800">
        &ldquo;{item.stated}&rdquo;
      </blockquote>
      <p className="mt-1.5 text-sm text-ink-400">{said ? `You, ${said}` : 'You'}</p>

      {/* The bridge from what they said to what we will check. Without this a
          watch card is their worry quoted back at them with our logo on it. */}
      <p className="mt-4 border-t border-ink-100 pt-3 text-sm leading-relaxed text-ink-600">
        <span className="font-mono text-2xs uppercase tracking-[0.1em] text-ink-400">
          What will test it
        </span>
        <br />
        {item.measured_by}
      </p>
      <p className="mt-2 text-sm font-medium text-clay-600">Needs {item.needs}.</p>
    </li>
  )
}

/**
 * What NEXUS refuses to ask for, and what it reads instead.
 *
 * `doc/08` §11 calls this one of the two things its cut adds: *"showing the
 * customer what NEXUS refuses to ask them is a product surface, not just an
 * internal rule."* It sits under Setup because that is where somebody is
 * already reading the list of things they did have to type.
 */
export function NotAskedPanel({ entries }: { entries: NotAsked[] }) {
  if (entries.length === 0) return null

  return (
    <section className="mt-8 rounded-2xl border border-ink-100 bg-bone-50 px-5 py-5">
      <p className="font-mono text-2xs uppercase tracking-[0.12em] text-ink-400">
        What we will not ask you for
      </p>
      <p className="mt-2 max-w-prose text-[0.95rem] leading-relaxed text-ink-600">
        These are measurements, not judgements. Asking you to type them would get a
        number you half-remember, and the point of this product is that every figure
        traces to something.
      </p>
      <ul className="mt-4 flex flex-col gap-2">
        {entries.map((entry) => (
          <li key={entry.what} className="text-[0.95rem] leading-relaxed text-ink-800">
            {entry.what}
            <span className="text-ink-500"> — read from {entry.source}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}

type State =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; setup: DirectorSetup }

export function SetupSection({
  department,
  tab,
  notAsked,
}: {
  department: string
  /** Which of the two tabs is open. They share one fetch. */
  tab: 'setup' | 'watchlist'
  notAsked: NotAsked[]
}) {
  const [state, setState] = useState<State>({ status: 'loading' })

  useEffect(() => {
    let live = true
    setState({ status: 'loading' })
    fetchSetup(department)
      .then((setup) => live && setState({ status: 'ready', setup }))
      .catch((caught: unknown) => {
        if (!live) return
        setState({
          status: 'error',
          message:
            caught instanceof AuthError ? caught.message : 'Could not read your answers.',
        })
      })
    return () => {
      live = false
    }
  }, [department])

  if (state.status === 'loading') return <Waiting>Reading your answers…</Waiting>

  if (state.status === 'error') {
    return (
      <div
        role="alert"
        className="rounded-xl border border-clay-300 bg-clay-100 px-4 py-3 text-sm text-clay-600"
      >
        {state.message}
      </div>
    )
  }

  const { facts, watch } = state.setup

  if (tab === 'watchlist') {
    return watch.length > 0 ? (
      <ul className="grid gap-4 sm:grid-cols-2">
        {watch.map((item) => (
          <Watch key={item.key} item={item} />
        ))}
      </ul>
    ) : (
      // Empty because the question is unanswered, which is a fact about the
      // answers and not about our access. Inventing a risk to fill the tab
      // would be the product telling a founder what to worry about.
      <p className="max-w-prose text-[0.95rem] leading-relaxed text-ink-600">
        Nothing here yet. This department asked one question about what is currently
        going wrong, and it has not been answered — so there is nothing being watched
        rather than nothing to watch.
      </p>
    )
  }

  return (
    <>
      {facts.length > 0 ? (
        <div className="rounded-2xl border border-ink-100 bg-white px-5 py-5 shadow-paper">
          <ul className="flex flex-col">
            {facts.map((fact) => (
              <Fact key={fact.key} fact={fact} />
            ))}
          </ul>
        </div>
      ) : (
        <p className="max-w-prose text-[0.95rem] leading-relaxed text-ink-600">
          Nobody has answered this department&rsquo;s questions yet. They are what turn
          its figures from generic into yours — a conversion rate needs your definition
          of a lead before it means anything.
        </p>
      )}

      <NotAskedPanel entries={notAsked} />
    </>
  )
}
