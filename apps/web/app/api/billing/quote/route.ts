import { proxyToApi } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * The costed summary for the Payment step (ADR 0076): the selected departments
 * and any additional tools, priced from the server-side `price` table. Proxied
 * rather than computed in the browser — the amounts are grounded in the DB, and
 * a second copy of the pricing maths here would be a figure nobody could
 * reproduce.
 */
export async function GET(request: Request) {
  return proxyToApi(request, {
    path: '/billing/quote',
    method: 'GET',
    unavailable: 'Cannot reach the billing service right now.',
  })
}
