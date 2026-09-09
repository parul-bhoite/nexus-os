'use client'

import { useEffect, useState } from 'react'
import { AuthError } from '@/lib/auth-client'
import { fetchBrain, type Brain } from '@/lib/settings-client'
import { Waiting } from '@/components/ui/Waiting'

/**
 * The Company Brain — panel 10 (`doc/13` §14), read-only.
 *
 * **`provenance` and `assumptions` are the point of the panel**, not a footer.
 * A brain the founder cannot audit is a brain they have to take on trust, and
 * this product's whole claim is that they never have to. So the assumptions are
 * shown as prominently as the facts: an assumption presented as a fact is the
 * one failure that would matter here.
 *
 * ## What it deliberately does not do
 *
 * **`doc/13` §14 asks for per-item sensitivity, passage counts and a delete.**
 * None of the three is here. `GET /onboarding/brain` serves the assembled brain
 * — profile, products, customers, goals, with its provenance — and the
 * per-fact view is the `fact` table, which this endpoint does not expose.
 *
 * **Deletion is P21's and must not be approximated.** Removing an item has to
 * fan out to its passages, its embeddings, cached answers and derivations; a
 * button that removed the row and left the embeddings would leave the fact
 * retrievable by the one path that matters, while the screen said it was gone.
 * That is worse than no button, so there is no button.
 */

function Section({ heading, body }: { heading: string; body: string | null }) {
  if (!body) return null

  return (
    <div className="border-t border-ink-100 py-4 first:border-t-0 first:pt-0">
      <p className="font-mono text-2xs uppercase tracking-[0.12em] text-ink-400">
        {heading}
      </p>
      <p className="mt-1.5 text-[0.95rem] leading-relaxed text-ink-800">{body}</p>
    </div>
  )
}

type State =
  | { status: 'loading' }
  | { status: 'error'; message: string; code: number }
  | { status: 'ready'; brain: Brain }

export function BrainCard() {
  const [state, setState] = useState<State>({ status: 'loading' })

  useEffect(() => {
    let live = true
    fetchBrain()
      .then((brain) => live && setState({ status: 'ready', brain }))
      .catch((caught: unknown) => {
        if (!live) return
        setState({
          status: 'error',
          message:
            caught instanceof AuthError ? caught.message : 'Could not read the Company Brain.',
          code: caught instanceof AuthError ? caught.status : 0,
        })
      })
    return () => {
      live = false
    }
  }, [])

  // 404 is a workspace whose onboarding has not finished. There is no brain
  // yet, which is a stage rather than a fault — and a red box about a missing
  // resource would read as breakage.
  if (state.status === 'error' && state.code === 404) {
    return (
      <section className="rounded-2xl border border-ink-100 bg-white px-5 py-5 shadow-paper">
        <h2 className="font-display text-lg text-ink-900">Company Brain</h2>
        <p className="mt-2 max-w-prose text-[0.95rem] leading-relaxed text-ink-600">
          Not built yet. It is assembled from your own answers at the end of setup, and
          every line in it names where it came from.
        </p>
      </section>
    )
  }

  if (state.status === 'loading') return <Waiting>Reading the Company Brain…</Waiting>

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

  const { brain } = state

  if (brain.generated_by === 'unavailable') {
    return (
      <section className="rounded-2xl border border-ink-100 bg-white px-5 py-5 shadow-paper">
        <h2 className="font-display text-lg text-ink-900">Company Brain</h2>
        <p className="mt-2 max-w-prose text-[0.95rem] leading-relaxed text-ink-600">
          {/* The reason comes from the API and already ends in a full stop —
              appending one produced "…something in it.. Nothing is filled in". */}
          Not assembled: {brain.unavailable_reason || 'no reason recorded.'} Nothing is
          filled in with a guess in the meantime.
        </p>
      </section>
    )
  }

  return (
    <section className="flex flex-col gap-4 rounded-2xl border border-ink-100 bg-white px-5 py-5 shadow-paper">
      <header>
        <h2 className="font-display text-lg text-ink-900">Company Brain</h2>
        <p className="mt-2 max-w-prose text-[0.95rem] leading-relaxed text-ink-600">
          What every director works from. Version {brain.version}, assembled from{' '}
          {brain.generated_by === 'answers' ? 'your own answers' : brain.generated_by}.
        </p>
        {brain.generated_by === 'answers' ? (
          // ADR 0011. A brain built without a model is a *complete* brain, not
          // a degraded one, and saying so matters: a founder who thinks they
          // are looking at a fallback will not correct it.
          <p className="mt-2 max-w-prose text-sm leading-relaxed text-ink-500">
            Built with no language model involved — you typed what you sell and who you
            sell it to, so assembling it invented nothing.
          </p>
        ) : null}
      </header>

      <div className="flex flex-col">
        <Section heading="Profile" body={brain.profile} />
        <Section heading="Products and services" body={brain.products_services} />
        <Section heading="Target customers" body={brain.target_customers} />
        <Section heading="Goals" body={brain.goals} />
      </div>

      {brain.assumptions.length > 0 ? (
        <div className="rounded-xl border border-gold-300 bg-gold-100 px-4 py-3">
          <p className="font-mono text-2xs uppercase tracking-[0.12em] text-clay-600">
            What it had to assume
          </p>
          <ul className="mt-2 flex flex-col gap-1.5">
            {brain.assumptions.map((assumption) => (
              <li key={assumption} className="text-[0.95rem] leading-relaxed text-ink-800">
                {assumption}
              </li>
            ))}
          </ul>
          <p className="mt-2 text-sm text-clay-600">
            Assumptions, not findings. Correcting one is the highest-value thing you can
            tell the product.
          </p>
        </div>
      ) : null}

      {brain.provenance.length > 0 ? (
        <details className="rounded-xl border border-ink-100 bg-bone-50 px-4 py-3">
          <summary className="cursor-pointer font-mono text-2xs uppercase tracking-[0.12em] text-ink-400">
            Where every line came from ({brain.provenance.length})
          </summary>
          <ul className="mt-3 flex flex-col gap-1.5">
            {brain.provenance.map((source) => (
              <li key={source} className="text-sm leading-relaxed text-ink-600">
                {source}
              </li>
            ))}
          </ul>
        </details>
      ) : null}

      <p className="border-t border-ink-100 pt-3 text-sm text-ink-400">
        Read-only here. Deleting an item has to remove its passages, its embeddings and
        anything derived from it — a button that removed the row and left the rest would
        say a fact was gone while it was still retrievable.
      </p>
    </section>
  )
}
