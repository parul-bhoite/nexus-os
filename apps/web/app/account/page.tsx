import type { Metadata } from 'next'
import { AccountPanel } from '@/components/auth/AccountPanel'

export const metadata: Metadata = {
  title: 'Your account',
  robots: { index: false, follow: false },
}

/**
 * Where signing in lands.
 *
 * Not a dashboard — there is nothing to put on one yet, and a skeleton with
 * zeroes in it would break the rule the whole product rests on. It shows the
 * account, the workspaces, and what is genuinely missing.
 *
 * The session is fetched client-side rather than server-side. A server component
 * could read the cookie and call the API, but it would then have to render either
 * a signed-in or a signed-out page *before* the client knew which, and a mismatch
 * shows as a flash of the wrong content. Fetching once on mount keeps one source
 * of truth.
 */
export default function AccountPage() {
  return (
    <>
      <h1 className="font-display text-title font-medium text-ink-900">Your account</h1>
      <p className="mt-3 max-w-xl text-[0.95rem] leading-relaxed text-ink-600">
        Everything below is read from the API. Nothing on this page is generated.
      </p>
      <div className="mt-10">
        <AccountPanel />
      </div>
    </>
  )
}
