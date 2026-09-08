import { proxyToApi } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * Read the pages `/start` fetched, and write the brief.
 *
 * No body, and none is read — the pages live on the session, server-side, so
 * that the grounding behind every line of the brief never passes through a
 * browser. See the finish route for why reading a body that was never sent is
 * its own bug: `request.json()` on an empty body throws before the proxy runs.
 */
export async function POST(request: Request) {
  return proxyToApi(request, {
    path: '/onboarding/agent/read',
    method: 'POST',
    timeoutMs: 180000,
    unavailable: 'Cannot reach the onboarding service right now.',
  })
}
