'use client'

import { useEffect } from 'react'
import { Button } from '@/components/ui/Button'
import { Logo } from '@/components/ui/Logo'

/**
 * The last line of defence for a render that throws.
 *
 * Without this file Next.js shows its own page: a stack trace in development
 * and an unbranded "500" in production. Neither tells a visitor what to do, and
 * the second one looks like the product is broken rather than that one screen
 * failed.
 *
 * It deliberately does NOT show `error.message`. A render error can carry an
 * API payload, a field name, or a fragment of whatever the user typed — and the
 * one crash this was written for was an API validation error being rendered as
 * a React child. The digest is shown instead: it is the id in the server logs,
 * so support can find the trace without the message reaching the screen.
 */
export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    // Reaches the browser console in development and the platform's log drain
    // in production. Not shown to the visitor.
    console.error('Unhandled render error', error)
  }, [error])

  return (
    <main id="main" tabIndex={-1} className="flex min-h-screen flex-col bg-bone-50 px-6 py-8 sm:px-10">
      <a href="/" className="w-fit" aria-label="NEXUS OS home">
        <Logo />
      </a>

      <div className="flex flex-1 items-center">
        <div className="w-full max-w-lg">
          <p className="font-mono text-2xs uppercase tracking-[0.14em] text-clay-600">
            Something broke
          </p>
          <h1 className="mt-3 font-display text-title font-medium text-ink-900">
            This page didn&rsquo;t load
          </h1>
          <p className="mt-3 text-[0.95rem] leading-relaxed text-ink-600">
            The fault is ours, not yours, and nothing you entered was lost. Try again
            &mdash; if it keeps happening, the reference below will let us find it.
          </p>

          {error.digest ? (
            <p className="mt-5 font-mono text-xs text-ink-500">
              Reference: <span className="text-ink-800">{error.digest}</span>
            </p>
          ) : null}

          <div className="mt-8 flex flex-wrap gap-3">
            <Button type="button" onClick={reset}>
              Try again
            </Button>
            <Button href="/" variant="secondary">
              Back to the start
            </Button>
          </div>
        </div>
      </div>
    </main>
  )
}
