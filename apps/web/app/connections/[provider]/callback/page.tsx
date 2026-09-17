import type { Metadata } from 'next'
import { ConnectionResult } from '@/components/settings/ConnectionResult'

export const metadata: Metadata = {
  title: 'Finishing the connection',
  robots: { index: false, follow: false },
}

/**
 * Where the vendor sends the browser back to — `doc/14` S9.
 *
 * **The redirect URI registered with the provider must be this page**, not the
 * API's callback. Both would work in the sense that the exchange completes; only
 * one of them lands a person on a page instead of on a JSON document. The API
 * route is still what verifies `state` and exchanges the code — this page hands
 * it the query string and renders what comes back.
 *
 * Outside the app shell on purpose. Somebody arriving here has just come from a
 * third party and is mid-flow; a full navigation with a header inviting them
 * elsewhere is how a connection gets abandoned one step from done.
 */
export default function ConnectionCallbackPage({
  params,
}: {
  params: { provider: string }
}) {
  return (
    <main className="mx-auto flex min-h-screen max-w-xl flex-col justify-center px-6">
      <h1 className="font-display text-2xl text-ink-900">Finishing the connection</h1>
      <ConnectionResult provider={params.provider} />
    </main>
  )
}
