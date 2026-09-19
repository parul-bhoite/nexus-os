import { AppShell } from '@/components/shell/AppShell'

/** The same shell as every other signed-in page (`doc/14` step 1). Missing it
 *  cost this route the nav panel, the header *and* the skip link's `#main`
 *  target — a page reachable from the nav that then stranded you, found when
 *  H16's skip-link audit counted the routes where the anchor dangles. */
export default function ReviewQueueLayout({ children }: { children: React.ReactNode }) {
  return <AppShell>{children}</AppShell>
}
