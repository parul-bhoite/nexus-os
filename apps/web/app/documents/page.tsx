import type { Metadata } from 'next'
import { DocumentLibrary } from '@/components/documents/DocumentLibrary'
import { PageHeader } from '@/components/ui/Page'

export const metadata: Metadata = {
  title: 'Your documents',
  robots: { index: false, follow: false },
}

/**
 * The other half of H4.
 *
 * Uploading existed only inside onboarding, which meant a workspace could send
 * documents exactly once — during setup, before anybody knew what the product
 * would ask for. After that the API was reachable and no screen reached it, so
 * the answer to "we have a new price list" was that there was nowhere to put
 * it.
 *
 * **Listing belongs here rather than being a later step.** `uploadDocument`
 * returns a stored-but-unreadable file as a *result* instead of an error,
 * because a scanned PDF with no text layer is on record and the reason is the
 * actionable part — and a screen that could not show that row would be throwing
 * away the thing the API went to trouble to report.
 *
 * Signed download is deliberately absent; it is M4, it needs its own BFF route
 * and its own decision about link lifetime, and guessing at either here would
 * be worse than leaving it off.
 */
export default function DocumentsPage() {
  return (
    <>
      <PageHeader
        title="Your documents"
        lede="What you have given NEXUS to read. A file is not readable by your workspace the moment it arrives: the classifier places what it can, withholds anything personal or financial by rule, and sends the rest to be reviewed by a person."
      />
      <DocumentLibrary />
    </>
  )
}
