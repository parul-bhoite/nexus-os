import type { Metadata } from 'next'
import { SettingsPanel } from '@/components/settings/SettingsPanel'

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
    <>
      {/* The page's h1 and its standfirst. Both lived inside the chrome this
          file used to draw itself, and moving to the shell took them with it —
          a regression, caught by a heading audit rather than by any test. */}
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
    </>
  )
}
