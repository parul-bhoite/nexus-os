import { proxyToApi } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * The brief, from the founder, when their site could not be read.
 *
 * Reachable only after a crawl that produced nothing — the API refuses it
 * otherwise, because offering it any earlier would be offering a way to skip
 * the read, and the read is what makes the brief correctable rather than
 * merely typed.
 *
 * No model call behind it, so no long timeout: the three answers *are* the
 * values.
 */
export async function POST(request: Request) {
  return proxyToApi(request, {
    path: '/onboarding/agent/describe',
    method: 'POST',
    body: await request.json(),
    unavailable: 'Cannot reach the onboarding service right now.',
  })
}
