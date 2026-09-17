import { proxyToApi } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * What this workspace is read from, and what it could be — `doc/14` S9.
 *
 * **This route did not exist until now**, which is why nothing in the browser
 * could reach the connector work at all: the OAuth round trip, sealed credential
 * storage and `crm_deal` were all built and testable, and a founder had no way
 * to press Connect. The BFF is one file per path, so a missing file is a 404 no
 * test suite sees.
 */
export async function GET(request: Request) {
  return proxyToApi(request, {
    path: '/connections',
    method: 'GET',
    unavailable: 'Cannot reach the connection service right now.',
  })
}
