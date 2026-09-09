import { proxyToApi } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * The workspace's own trail — panel 12.
 *
 * The gate is upstream and is `require_executive_surface`, which is **wider
 * than `doc/08` §8C specifies**: that says the audit log is Owner-visible only,
 * and an Executive can currently read it. Recorded rather than narrowed here,
 * because tightening a permission belongs where the permission is decided and
 * P21 owns making the log access-controlled in its own right.
 */
export async function GET(request: Request) {
  return proxyToApi(request, {
    path: '/audit-log',
    method: 'GET',
    unavailable: 'Cannot reach the audit service right now.',
  })
}
