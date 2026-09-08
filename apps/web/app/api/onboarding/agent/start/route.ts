import { proxyToApi } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * Crawl the domain and read it. The slow one — a crawl plus two model calls.
 */
export async function POST(request: Request) {
  return proxyToApi(request, {
    path: '/onboarding/agent/start',
    method: 'POST',
    timeoutMs: 180000,
    unavailable: 'Cannot reach the onboarding service right now.',
  })
}
