import { proxyToApi } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * The whole onboarding question catalogue in one call.
 *
 * Every question is returned together — across all stages and all departments —
 * each tagged with the `department` that owns its answer and the `scope` where
 * it will be stored. The combined onboarding flow filters this client-side to
 * the Areas of Interest the founder picked (plus the company-level questions,
 * whose `department` is `null`); the API still decides what any caller may read
 * and write, so a field this flow hides is a presentation choice and never the
 * boundary.
 */
export async function GET(request: Request) {
  return proxyToApi(request, {
    path: '/onboarding/questions',
    method: 'GET',
    unavailable: 'Cannot reach the onboarding service right now.',
  })
}
