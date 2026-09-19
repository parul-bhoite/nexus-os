import { proxyToApi } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * The chunks withheld from this workspace, awaiting a person.
 *
 * Its own file because App Router matches on path: `app/api/documents/route.ts`
 * does not serve `/api/documents/review-queue`, and a missing route here is a
 * 404 that neither test suite can see — the component's fetch is mocked and the
 * API's own tests never touch this app.
 *
 * The excerpt in each item is content the classifier withheld *because nobody
 * has decided who may see it*, so this route is as access-controlled as any
 * other: `proxyToApi` forwards the session cookie and the API scopes the read
 * to the caller's workspace in the database.
 */
export async function GET(request: Request) {
  return proxyToApi(request, {
    path: '/documents/review-queue',
    method: 'GET',
    unavailable: 'Cannot reach the document service right now.',
  })
}
