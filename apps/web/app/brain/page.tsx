import type { Metadata } from 'next'
import { CompanyBrainPage } from '@/components/brain/CompanyBrainPage'
import { PageHeader } from '@/components/ui/Page'

export const metadata: Metadata = {
  title: 'Company Brain',
  robots: { index: false, follow: false },
}

/**
 * ADR 0069 phase 2: every fact NEXUS holds, with its provenance.
 *
 * `components/dashboard/CompanyBrain.tsx` on `/dashboard` is the glance —
 * four fields and the assumptions that need auditing. This is the whole
 * thing: those same fields alongside every answered threshold, searchable,
 * each with where it came from and (stretch) a relationship graph built from
 * the same data. Nothing here is a second source of truth — `lib/brain-
 * facts.ts` reads the same two endpoints that panel does.
 */
export default function BrainPage() {
  return (
    <>
      <PageHeader
        title="Company Brain"
        lede="Every fact NEXUS holds about your company, and where it came from. Deleting or correcting one here is not yet available — for now, each row says where it can be changed."
      />
      <CompanyBrainPage />
    </>
  )
}
