import type { Metadata } from 'next'
import { AdminPricing } from '@/components/admin/AdminPricing'
import { Logo } from '@/components/ui/Logo'

export const metadata: Metadata = {
  title: 'Pricing — Admin',
  robots: { index: false, follow: false },
}

export const dynamic = 'force-dynamic'

/**
 * The platform-admin rate-card editor (ADR 0076/0077).
 *
 * A standalone operator screen rather than part of the workspace shell: editing
 * global prices is a platform act, not a workspace one, so it does not belong
 * under a tenant's dashboard chrome. Middleware requires a session; the API
 * requires the caller be on the platform-admin allowlist — a signed-in
 * non-admin lands here and `AdminPricing` renders its "not a platform admin"
 * branch from the API's 403.
 */
export default function AdminPricingPage() {
  return (
    <main id="main" tabIndex={-1} className="min-h-screen bg-bone-100">
      <header className="border-b border-bone-200 bg-white px-6 py-4 sm:px-8">
        <div className="mx-auto flex w-full max-w-3xl items-center justify-between gap-3">
          <Logo />
          <span className="rounded-full bg-steel-100 px-3 py-1 font-mono text-[10px] uppercase tracking-[0.1em] text-steel-700">
            Admin
          </span>
        </div>
      </header>
      <div className="mx-auto w-full max-w-3xl px-6 py-10 sm:px-8">
        <h1 className="font-display text-page text-ink-900">Pricing</h1>
        <p className="mt-2 max-w-read text-body text-ink-600">
          The rate card the onboarding Payment step quotes from. Changes take effect on the next
          quote; existing subscriptions keep the amount they were charged.
        </p>
        <div className="mt-8">
          <AdminPricing />
        </div>
      </div>
    </main>
  )
}
