import type { Metadata } from 'next'
import { SettingsPanel } from '@/components/settings/SettingsPanel'
import { PageHeader } from '@/components/ui/Page'

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
      <PageHeader
        title="Settings"
        lede="Proving your domain, the people in your company, and the assumptions every figure on every dashboard is cut against."
      />
      <div className="mt-6">
        <SettingsPanel />
      </div>
    </>
  )
}
