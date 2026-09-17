import { proxyToApi } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * Everything this workspace has recorded — `doc/15` S10.1.
 *
 * The BFF is per-route by design: every path the browser may reach is a file
 * here, so widening what the client can call is a deliberate act rather than a
 * wildcard nobody reviews. That also means **a missing file is a 404 no test in
 * either suite can see** — vitest mocks `fetch` and pytest calls the API
 * directly, so the whole ops layer worked end to end while the page showed
 * "Could not read what you have recorded." The browser found it.
 *
 * The default timeout is right: this is two indexed reads and reaches no model.
 */
export async function GET(request: Request) {
  return proxyToApi(request, {
    path: '/ops',
    method: 'GET',
    unavailable: 'Cannot reach the workspace service right now.',
  })
}
