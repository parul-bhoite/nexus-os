import { proxyToApi } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * The public price list the Areas step shows (ADR 0076): each area's monthly
 * price and the tools it includes. Proxied rather than computed in the browser
 * for the same reason as the quote — the amounts are grounded in the server-side
 * `price` table, never invented client-side.
 */
export async function GET(request: Request) {
  return proxyToApi(request, {
    path: '/billing/rate-card',
    method: 'GET',
    unavailable: 'Cannot reach the billing service right now.',
  })
}
