import type { Metadata } from 'next'
import { DashboardLanding } from '@/components/dashboard/DashboardLanding'

export const metadata: Metadata = {
  title: 'Your dashboard',
  robots: { index: false, follow: false },
}

/**
 * Where signing in and finishing setup both lead.
 *
 * It holds nothing of its own — it asks the API which director this person
 * belongs to and forwards them. The decision is server-side because it is the
 * same fact that authorises the page it forwards to, and two sources for one
 * fact is how a redirect starts disagreeing with a permission check.
 *
 * The header and page frame it used to draw itself now come from the shell
 * (`doc/14` step 1), so this is the content and nothing else.
 */
export default function DashboardPage() {
  return <DashboardLanding />
}
