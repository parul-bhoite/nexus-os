import type { Metadata } from 'next'
import Link from 'next/link'
import { SettingsPanel } from '@/components/settings/SettingsPanel'
import { Logo } from '@/components/ui/Logo'

export const metadata: Metadata = {
  title: 'Settings',
  robots: { index: false, follow: false },
}

/**
 * The screen the rest of the product kept pointing at.
 *
 * Finding F3. `/register-company` said twice that proving the domain happens
 * "in Settings", and `POST /invitations` refused with *"Settings has the DNS
 * record to add"* — while no `/settings` route existed, the verification card
 * was written and imported by nothing, and no screen anywhere sent an
 * invitation. Because the domain gate is genuinely enforced server-side, the
 * missing page was not cosmetic: invite, accept and per-member scoping could
 * not be exercised through a browser at all.
 *
 * Client-fetched for the same reason as `/account` and `/onboarding`: a server
 * component would have to render either the signed-in or the signed-out view
 * before the client knew which, and a mismatch shows as a flash of the wrong
 * screen.
 */
export default function SettingsPage() {
  return (
    <main className="min-h-screen bg-bone-50">
      <div className="mx-auto max-w-3xl px-6 py-8 sm:px-10">
        <header className="flex flex-wrap items-center justify-between gap-4 border-b border-ink-100 pb-6">
          <Link
            href="/"
            className="inline-flex rounded-lg focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-gold-500"
            aria-label="NEXUS OS home"
          >
            <Logo />
          </Link>
          <div className="flex items-center gap-4">
            <Link
              href="/dashboard"
              className="text-sm font-medium text-steel-600 underline decoration-steel-300 underline-offset-2 hover:text-steel-700"
            >
              Dashboard
            </Link>
            <Link
              href="/account"
              className="text-sm font-medium text-steel-600 underline decoration-steel-300 underline-offset-2 hover:text-steel-700"
            >
              Account
            </Link>
          </div>
        </header>

        <div className="py-10">
          <h1 className="font-display text-title font-medium text-ink-900">Settings</h1>
          <p className="mt-3 max-w-prose text-[0.95rem] leading-relaxed text-ink-600">
            Proving your domain, the people in your company, and the assumptions every
            figure on every dashboard is cut against. The first two reach beyond your own
            account, which is why the domain check gates them; the third decides what your
            numbers mean.
          </p>

          <div className="mt-10">
            <SettingsPanel />
          </div>
        </div>
      </div>
    </main>
  )
}
