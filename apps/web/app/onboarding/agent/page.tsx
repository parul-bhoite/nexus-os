import { AgentOnboarding } from '@/components/onboarding/AgentOnboarding'

export const dynamic = 'force-dynamic'

export const metadata = { title: 'Setting up your workspace — NEXUS OS' }

/**
 * The guided onboarding route.
 *
 * No parameters. Which company is being set up is decided by the session's
 * workspace, server-side — so this URL cannot be used to research somebody
 * else's domain, and a bookmark or a refresh resumes the journey already in
 * progress rather than starting a second one.
 */
export default function Page() {
  return <AgentOnboarding />
}
