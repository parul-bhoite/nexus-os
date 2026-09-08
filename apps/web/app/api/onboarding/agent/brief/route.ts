import { proxyToApi } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * Confirm the brief, correcting any line. A correction outranks the crawl.
 */
export async function POST(request: Request) {
  return proxyToApi(request, {
    path: '/onboarding/agent/brief',
    method: 'POST',
    body: await request.json(),
    unavailable: 'Cannot reach the onboarding service right now.',
  })
}
