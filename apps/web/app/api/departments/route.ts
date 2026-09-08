import { proxyToApi } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * The department catalogue, for the company form.
 *
 * Proxied like everything else rather than fetched from the API directly, so
 * one origin serves the whole app and no CORS rule has to exist for a list of
 * seven nouns.
 *
 * A fixed list with no tenant data in it, asked for in the window between
 * signing up and having a workspace — see the API route for why it needs no
 * scope, and why hardcoding these seven in the browser would re-create
 * finding F13.
 */
export async function GET(request: Request) {
  return proxyToApi(request, {
    path: '/departments',
    method: 'GET',
    unavailable: 'Cannot reach the account service right now.',
  })
}
