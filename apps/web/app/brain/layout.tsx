import { AppShell } from '@/components/shell/AppShell'

/** Same shell as every other signed-in page (`doc/14` step 1) — see
 *  `app/documents/layout.tsx` for why this one line matters more than it
 *  looks: without it the page loses the nav panel, the header and the
 *  skip-link's `#main` target. */
export default function BrainLayout({ children }: { children: React.ReactNode }) {
  return <AppShell>{children}</AppShell>
}
