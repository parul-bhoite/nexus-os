import { proxyToApi } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * The next question, chosen and worded by the model.
 */
export async function GET(request: Request) {
  return proxyToApi(request, {
    path: '/onboarding/agent/next',
    method: 'GET',
    timeoutMs: 60000,
    unavailable: 'Cannot reach the onboarding service right now.',
  })
}
