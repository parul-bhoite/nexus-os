import type { Metadata } from 'next'
import { WorkRecorder } from '@/components/ops/WorkRecorder'
import { PageHeader } from '@/components/ui/Page'

export const metadata: Metadata = {
  title: 'Your work',
  robots: { index: false, follow: false },
}

/**
 * The first screen in NEXUS that writes the customer's own records.
 *
 * `doc/15` S10.1. Every other surface shows something we fetched — a crawl we
 * performed, a provider we queried, answers given during onboarding. This one
 * takes projects and tasks a founder types and gives them back, which is what
 * turns Operations from a department of locked tiles into one with figures.
 *
 * **The ops layer fails on adoption, not on an API.** That is not a reason to
 * build it later; it is the reason this page exists at all and the reason its
 * copy is about getting the first row in rather than about managing a
 * portfolio. Nothing here is a project-management product — no assignments, no
 * comments, no notifications — because the 23 capabilities blocked on this need
 * records to compute from, and every feature past that is one more thing to
 * adopt before any figure appears.
 */
export default function WorkPage() {
  return (
    <>
      <PageHeader
        title="Your work"
        lede="Projects and tasks you record here are counted on the Operations tiles. NEXUS counts what is written down — it has no way of knowing what is not, so the figures say “recorded” rather than claiming to describe the whole company."
      />
      <WorkRecorder />
    </>
  )
}
