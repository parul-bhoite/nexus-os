import { proxyToApi } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * The dummy payment gateway (ADR 0076). Records a paid subscription snapshot and
 * returns the resulting entitlement; there is no real provider wired yet, so
 * this always succeeds. The amount is taken server-side from the current quote —
 * the browser never sends a price.
 */
export async function POST(request: Request) {
  return proxyToApi(request, {
    path: '/billing/pay',
    method: 'POST',
    unavailable: 'Cannot reach the billing service right now.',
  })
}
