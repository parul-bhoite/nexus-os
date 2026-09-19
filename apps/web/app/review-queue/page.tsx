import type { Metadata } from 'next'
import { ReviewQueue } from '@/components/review/ReviewQueue'
import { PageHeader } from '@/components/ui/Page'

export const metadata: Metadata = {
  title: 'Waiting for review',
  robots: { index: false, follow: false },
}

/**
 * H4, and the half of the classifier that had nowhere to happen.
 *
 * `GET /documents/review-queue` and its decision endpoint were complete,
 * authorised and tested, and no client called either — so every chunk the
 * classifier declined to place was withheld to L5 permanently. ADR 0051 made
 * that visible by wiring `rules.propose` in: the confident majority started
 * flowing, which left the remainder sitting in a queue whose existence nothing
 * in the product admitted to.
 *
 * Its own route rather than a Settings tab. Reviewing is recurring work that
 * belongs beside the documents it concerns, and burying it under a settings
 * screen would make the product's central safety control the least reachable
 * thing in it.
 */
export default function ReviewQueuePage() {
  return (
    <>
      <PageHeader
        title="Waiting for review"
        lede="What the classifier would not file on its own. Anything it read as personal or financial is here by rule, however sure it was — and so is anything it could not place confidently. Until you decide, none of it is readable by anyone but the person who uploaded it."
      />
      <ReviewQueue />
    </>
  )
}
