import { AppShell } from '@/components/shell/AppShell'

/**
 * Every signed-in dashboard route renders inside the shell.
 *
 * A layout rather than a wrapper each page opts into: `doc/14` step 1 replaces
 * the per-page header that three pages had each written their own copy of, and
 * an opt-in shell is one a new route forgets. Put here, a page added tomorrow
 * gets the panel, the session handling and the single `/api/dashboards` fetch
 * without knowing they exist.
 */
export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return <AppShell>{children}</AppShell>
}
