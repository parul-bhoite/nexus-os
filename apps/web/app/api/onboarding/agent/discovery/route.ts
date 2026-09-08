import { proxyToApi } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * The one free-text turn, interpreted before anything is stored.
 */
export async function POST(request: Request) {
  return proxyToApi(request, {
    path: '/onboarding/agent/discovery',
    method: 'POST',
    body: await request.json(),
    timeoutMs: 60000,
    unavailable: 'Cannot reach the onboarding service right now.',
  })
}
