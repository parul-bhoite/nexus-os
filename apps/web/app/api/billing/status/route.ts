import { proxyToApi } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * Whether this workspace is entitled to the dashboard — paid, or inside an
 * active free trial. The dashboard gate and the onboarding resume both read
 * this (ADR 0076 extends the ADR 0075 completion gate).
 */
export async function GET(request: Request) {
  return proxyToApi(request, {
    path: '/billing/status',
    method: 'GET',
    unavailable: 'Cannot reach the billing service right now.',
  })
}
