import { proxyToApi, readJson } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * The reporting assumptions every tile's window is cut against.
 *
 * `doc/13` §13, ADR 0025. Four of doc 05 §1's seven required global assumptions
 * had no home in the product, so no working drawer could state the window its
 * arithmetic was computed over. This is the screen that fills them in.
 *
 * Readable by anyone in the workspace and writable only by an administrator —
 * the split is enforced upstream, and this route does not repeat it. A number is
 * only checkable if the assumptions under it are visible to the person checking,
 * which is why a Contributor may read what they may not change.
 */
export async function GET(request: Request) {
  return proxyToApi(request, {
    path: '/companies/current/reporting',
    method: 'GET',
    unavailable: 'Cannot reach the account service right now.',
  })
}

export async function PUT(request: Request) {
  return proxyToApi(request, {
    path: '/companies/current/reporting',
    method: 'PUT',
    body: (await readJson(request)) ?? {},
    unavailable: 'Cannot reach the account service right now.',
  })
}
