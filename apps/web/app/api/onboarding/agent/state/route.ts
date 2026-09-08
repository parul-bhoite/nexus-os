import { proxyToApi } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * Where the journey is. Safe to poll; works with no model configured.
 */
export async function GET(request: Request) {
  return proxyToApi(request, {
    path: '/onboarding/agent/state',
    method: 'GET',
    unavailable: 'Cannot reach the onboarding service right now.',
  })
}
