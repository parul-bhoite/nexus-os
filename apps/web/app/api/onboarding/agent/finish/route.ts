import { proxyToApi } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * Assemble the Persona, the Brain and the context later agents read.
 *
 * No body, and none is read. The endpoint takes its input from the session it
 * is closing, so the client posts nothing — and `request.json()` on an empty
 * body throws, which turned the last click of onboarding into a 500 that never
 * reached the API at all.
 */
export async function POST(request: Request) {
  return proxyToApi(request, {
    path: '/onboarding/agent/finish',
    method: 'POST',
    timeoutMs: 240000,
    unavailable: 'Cannot reach the onboarding service right now.',
  })
}
