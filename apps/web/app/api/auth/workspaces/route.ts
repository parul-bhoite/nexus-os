import { proxyToApi } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * The entities this login holds — ADR 0026.
 *
 * Upstream this depends on the session rather than on a scope, deliberately:
 * somebody switching *away* from a workspace whose access was revoked has no
 * valid scope and still needs this list. Refusing them would trap them on a
 * company they cannot open.
 */
export async function GET(request: Request) {
  return proxyToApi(request, {
    path: '/auth/workspaces',
    method: 'GET',
    unavailable: 'Cannot reach the account service right now.',
  })
}
