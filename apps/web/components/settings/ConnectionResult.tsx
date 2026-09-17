'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'

/**
 * Completes the authorisation the vendor just sent the browser back from.
 *
 * **The query string is forwarded whole and never rebuilt.** `state` is signed
 * and bound to workspace, person and provider, and `code` is single-use — a
 * client that parsed and reassembled either would be a second place for that
 * check to go subtly wrong, and the failure would be an authorisation accepted
 * that should not have been.
 *
 * Runs once. A `code` is spent on first exchange, so a re-run on re-render would
 * ask the vendor to honour it twice and show the founder a failure for a
 * connection that actually succeeded.
 */
export function ConnectionResult({ provider }: { provider: string }) {
  const [state, setState] = useState<'working' | 'done' | 'failed'>('working')
  const [message, setMessage] = useState('')

  useEffect(() => {
    let live = true
    const query = window.location.search

    async function finish() {
      try {
        const response = await fetch(
          `/api/connections/${encodeURIComponent(provider)}/callback${query}`,
          { credentials: 'same-origin', cache: 'no-store' },
        )
        const payload = await response.json().catch(() => null)
        if (!live) return

        if (!response.ok) {
          setState('failed')
          setMessage(payload?.detail ?? 'That connection could not be completed.')
          return
        }
        setState('done')
        setMessage(payload?.message ?? 'Connected.')
      } catch {
        if (!live) return
        setState('failed')
        // A transport failure, not a refusal — the API never got to have an
        // opinion, and saying "refused" would be a guess about somebody's data.
        setMessage('We could not reach NEXUS to finish this. Nothing was changed.')
      }
    }

    void finish()
    return () => {
      live = false
    }
  }, [provider])

  return (
    <>
      <p
        role={state === 'failed' ? 'alert' : 'status'}
        className={`mt-3 text-sm leading-relaxed ${
          state === 'failed' ? 'text-clay-600' : 'text-ink-600'
        }`}
      >
        {state === 'working' ? 'Checking with the provider…' : message}
      </p>

      {state !== 'working' ? (
        <Link
          href="/settings"
          className="mt-6 self-start rounded-lg border border-ink-200 px-4 py-2 text-sm font-medium text-ink-700 hover:border-ink-300 hover:text-ink-900"
        >
          Back to settings
        </Link>
      ) : null}
    </>
  )
}
