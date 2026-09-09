import { proxyToApi, readJson } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * How NEXUS talks to you — panel 2.
 *
 * Every field is a `persona.*` column and **none of them authorises anything**
 * (`doc/06` §2.6). That is why this is the one settings surface with no
 * administrator gate: changing it cannot widen what anybody sees, and
 * `fields.py` fails the process at import if a role-shaped key is ever added to
 * that namespace.
 */
export async function GET(request: Request) {
  return proxyToApi(request, {
    path: '/auth/preferences',
    method: 'GET',
    unavailable: 'Cannot reach the account service right now.',
  })
}

export async function PUT(request: Request) {
  return proxyToApi(request, {
    path: '/auth/preferences',
    method: 'PUT',
    body: (await readJson(request)) ?? {},
    unavailable: 'Cannot reach the account service right now.',
  })
}
