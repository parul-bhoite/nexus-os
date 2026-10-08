import { proxyToApi } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * The workspace's measured connector insights (ADR 0085). Ungated, like the
 * company brain it sits beside — the Brain page reads it before payment. The
 * API scopes it to the caller's own workspace; this route only forwards the
 * session cookie.
 */
export async function GET(request: Request) {
  return proxyToApi(request, {
    path: '/insights',
    method: 'GET',
    unavailable: 'Cannot load your insights right now.',
  })
}
