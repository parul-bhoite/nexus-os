import { OnboardingEntry } from '@/components/onboarding/OnboardingEntry'

export const dynamic = 'force-dynamic'

export const metadata = { title: 'Setting up your workspace — NEXUS OS' }

/**
 * The standalone guided-onboarding route.
 *
 * ADR 0069 (phase 1) replaces the ADR 0067 catalogue with a conversation and a
 * live Company Brain panel. Rather than issuing a server redirect to
 * `/register-company`, this mounts the same `OnboardingEntry` directly — it
 * resolves the founder's actual position (company created yet or not) from the
 * API on mount regardless of which of the two URLs was opened, so a bookmark
 * or a refresh of this route resumes exactly where `/register-company` would
 * too.
 *
 * The eight-phase `AgentOnboarding` component this used to render is
 * deliberately left in the tree, unmounted, with its own tests intact — ADR
 * 0069 retires it in a dedicated change, not this one.
 */
export default function Page() {
  return <OnboardingEntry />
}
