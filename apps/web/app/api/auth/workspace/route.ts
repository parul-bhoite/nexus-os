import { proxyToApi, readJson } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * Move the session's pointer to another entity — ADR 0026.
 *
 * The route came back with multi-entity, having been deleted with `doc/11` Q9
 * along with `_teardown_on_switch` and I5's cache-invalidation requirement.
 *
 * The membership is re-read upstream rather than trusted from the body, so a
 * forged `workspace_id` grants nothing. What the caller gets back is the new
 * list, with `active` moved.
 */
export async function POST(request: Request) {
  return proxyToApi(request, {
    path: '/auth/workspace',
    method: 'POST',
    body: (await readJson(request)) ?? {},
    unavailable: 'Cannot reach the account service right now.',
  })
}
