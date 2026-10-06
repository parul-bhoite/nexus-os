import type { Metadata } from 'next'
import { OnboardingEntry } from '@/components/onboarding/OnboardingEntry'

export const metadata: Metadata = {
  title: 'Create your company',
  robots: { index: false, follow: false },
}

export const dynamic = 'force-dynamic'

/**
 * Entry point for the conversational onboarding flow (ADR 0069, phase 1).
 *
 * `OnboardingEntry` resolves the founder's real position itself on mount — see
 * its own doc comment for why this and `/onboarding/agent/page.tsx` both
 * simply mount it rather than one redirecting to the other. Supersedes
 * `StartFlow`, the ADR 0067 catalogue, which stays in the tree (unmounted)
 * until a dedicated removal change.
 */
export default function RegisterCompanyPage() {
  return <OnboardingEntry />
}
