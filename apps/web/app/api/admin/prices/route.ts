import { proxyToApi } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * The full rate card for the admin pricing screen (ADR 0076/0077). The API
 * gates this on the platform-admin allowlist and 403s otherwise — the check is
 * server-side on the caller's own email, never anything this proxy forwards.
 */
export async function GET(request: Request) {
  return proxyToApi(request, {
    path: '/admin/prices',
    method: 'GET',
    unavailable: 'Cannot reach the billing service right now.',
  })
}
