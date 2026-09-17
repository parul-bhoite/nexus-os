import { AppShell } from '@/components/shell/AppShell'

/** Recording work renders inside the same shell as everything else signed in
 *  — `doc/14` step 1's rule, and the reason three pages no longer draw three
 *  headers that drift apart. */
export default function WorkLayout({ children }: { children: React.ReactNode }) {
  return <AppShell>{children}</AppShell>
}
