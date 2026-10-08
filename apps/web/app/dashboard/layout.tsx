import { redirect } from 'next/navigation'
import { AppShell } from '@/components/shell/AppShell'
import { serverEntitled } from '@/lib/entitlement-server'

/**
 * Every signed-in dashboard route renders inside the shell.
 *
 * A layout rather than a wrapper each page opts into: `doc/14` step 1 replaces
 * the per-page header that three pages had each written their own copy of, and
 * an opt-in shell is one a new route forgets. Put here, a page added tomorrow
 * gets the panel, the session handling and the single `/api/dashboards` fetch
 * without knowing they exist.
 *
 * **The entitlement page gate (ADR 0084).** Before the shell renders, an
 * unentitled workspace is redirected to finish payment — the redirect-before-
 * render half of a defense-in-depth gate whose authority is the API's 402.
 * `serverEntitled` fails open, so this never locks out a paying customer on a
 * billing-service blip; the API gate still refuses the data if it must.
 */
export default async function DashboardLayout({ children }: { children: React.ReactNode }) {
  if (!(await serverEntitled())) {
    redirect('/onboarding/agent')
  }
  return <AppShell>{children}</AppShell>
}
