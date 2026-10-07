import { proxyToApi } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * Start the 7-day free trial instead of paying (ADR 0076). Records a trial
 * subscription with a server-set expiry and returns the entitlement; the
 * expiry is decided by the API, never sent by the browser.
 */
export async function POST(request: Request) {
  return proxyToApi(request, {
    path: '/billing/trial',
    method: 'POST',
    unavailable: 'Cannot reach the billing service right now.',
  })
}
