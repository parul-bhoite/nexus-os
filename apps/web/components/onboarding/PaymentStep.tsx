'use client'

import { useEffect, useState } from 'react'
import { PresenceMark } from '@/components/onboarding/OnboardingAura'
import { fetchQuote, pay, startTrial, formatMinor, type Quote, type QuoteLine } from '@/lib/billing-client'

/**
 * Step 7 of the stepped onboarding (ADR 0076): the costed summary and the
 * (dummy) payment gateway.
 *
 * The amounts are fetched from `/api/billing/quote` — computed server-side from
 * the `price` table against the areas and tools the founder chose — and shown
 * here read-only; the browser never sends a price. A founder either pays (the
 * dummy gateway always succeeds) or starts a 7-day free trial; both grant entry
 * and the orchestrator forwards to the dashboard.
 */

type Load =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; quote: Quote }

export function PaymentStep({ onDone }: { onDone: () => void }) {
  const [load, setLoad] = useState<Load>({ status: 'loading' })
  const [busy, setBusy] = useState<null | 'pay' | 'trial'>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  useEffect(() => {
    let live = true
    fetchQuote()
      .then((quote) => {
        if (live) setLoad({ status: 'ready', quote })
      })
      .catch((error: unknown) => {
        if (live)
          setLoad({
            status: 'error',
            message: error instanceof Error ? error.message : 'Could not load your plan.',
          })
      })
    return () => {
      live = false
    }
  }, [])

  async function act(kind: 'pay' | 'trial') {
    setBusy(kind)
    setActionError(null)
    try {
      await (kind === 'pay' ? pay() : startTrial())
      onDone()
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'Something went wrong — try again.')
      setBusy(null)
    }
  }

  if (load.status === 'loading') return <Loading />
  if (load.status === 'error') {
    return (
      <div role="alert" className="rounded-data border border-clay-300 bg-clay-100 px-6 py-5">
        <h3 className="font-medium text-ink-800">Your plan did not load</h3>
        <p className="mt-2 text-sm text-clay-600">{load.message}</p>
      </div>
    )
  }

  const { quote } = load
  const billed = quote.line_items.filter((l) => !l.included)
  const included = quote.line_items.filter((l) => l.included)
  const anyUnavailable = billed.some((l) => l.unavailable)

  return (
    <div className="flex flex-col gap-6">
      <div>
        <div className="flex items-center gap-3">
          <PresenceMark state="ready" size={30} />
          <h1 className="font-display text-page text-ink-900">Your plan</h1>
        </div>
        <p className="mt-2 max-w-read text-body text-ink-600">
          Priced from the areas you chose and the tools you added. Tools that come with an area are
          included; tools from other areas are added below. You can change any of this later.
        </p>
      </div>

      <div className="rounded-2xl border border-bone-300 bg-white/90 p-5">
        <ul className="divide-y divide-bone-200">
          {billed.map((line) => (
            <LineRow key={`${line.kind}:${line.key}`} line={line} currency={quote.currency} />
          ))}
        </ul>

        {included.length > 0 && (
          <div className="mt-4 border-t border-bone-200 pt-4">
            <p className="font-mono text-2xs uppercase tracking-[0.12em] text-ink-400">
              Included with your areas
            </p>
            <ul className="mt-2 flex flex-wrap gap-2">
              {included.map((line) => (
                <li
                  key={`${line.kind}:${line.key}`}
                  className="rounded-full bg-bone-100 px-3 py-1 text-xs text-ink-600"
                >
                  {line.label} · included
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="mt-5 flex items-end justify-between border-t border-bone-200 pt-4">
          <span className="text-sm text-ink-600">Total</span>
          <span className="font-display text-title text-ink-900">
            {formatMinor(quote.total_minor, quote.currency)}
            <span className="ml-1 text-sm font-normal text-ink-500">/ month</span>
          </span>
        </div>
      </div>

      {anyUnavailable && (
        <p className="text-sm text-clay-600">
          Some items have no price set yet and are not in the total. You can still start a free trial.
        </p>
      )}

      {actionError && (
        <p role="alert" className="text-sm text-clay-600">
          {actionError}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => void act('pay')}
          disabled={busy !== null}
          className="min-h-[2.75rem] rounded-full bg-ink px-7 text-sm font-medium text-bone-50 shadow-paper transition-transform hover:scale-[1.02] disabled:opacity-50"
        >
          {busy === 'pay'
            ? 'Processing…'
            : `Pay ${formatMinor(quote.total_minor, quote.currency)} / month`}
        </button>
        <button
          type="button"
          onClick={() => void act('trial')}
          disabled={busy !== null}
          className="min-h-[2.75rem] rounded-full border border-bone-300 px-5 text-sm text-ink-600 hover:border-steel-400 disabled:opacity-50"
        >
          {busy === 'trial' ? 'Starting…' : 'Start 7-day free trial'}
        </button>
      </div>
      <p className="text-xs text-ink-400">
        This is a demo gateway — no card is charged. Paying or starting the trial opens your
        workspace.
      </p>
    </div>
  )
}

function LineRow({ line, currency }: { line: QuoteLine; currency: string }) {
  return (
    <li className="flex items-center justify-between py-3">
      <span className="text-sm text-ink-800">
        {line.label}
        {line.kind === 'tool' && (
          <span className="ml-2 font-mono text-2xs uppercase tracking-wider text-ink-400">added tool</span>
        )}
      </span>
      <span className="text-sm tabular-nums text-ink-700">
        {line.unavailable ? (
          <span className="text-clay-600">price not set</span>
        ) : (
          <>
            {formatMinor(line.amount_minor, currency)}
            <span className="ml-1 text-ink-400">/ mo</span>
          </>
        )}
      </span>
    </li>
  )
}

function Loading() {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <PresenceMark state="thinking" size={30} />
        <h1 className="font-display text-page text-ink-900">Your plan</h1>
      </div>
      <div aria-hidden className="flex flex-col gap-3">
        <div className="h-24 w-full animate-breathe rounded-2xl bg-bone-200" />
        <div className="h-11 w-56 animate-breathe rounded-full bg-bone-200" />
      </div>
    </div>
  )
}
