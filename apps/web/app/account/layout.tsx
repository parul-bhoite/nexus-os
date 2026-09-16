import { AppShell } from '@/components/shell/AppShell'

/**
 * The account page renders inside the same shell as the dashboard.
 *
 * `doc/14` step 1. One chrome for every signed-in surface: three pages had
 * each written their own header, and the three had already drifted — this one
 * linked "Workspace setup" where another did not, so the same person saw a
 * different set of destinations depending which page they were on.
 */
export default function AccountLayout({ children }: { children: React.ReactNode }) {
  return <AppShell>{children}</AppShell>
}
