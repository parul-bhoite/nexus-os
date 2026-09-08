import { proxyToApi, readJson } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * The tool catalogue, ordered for this company, with what it has declared.
 *
 * Proxied rather than held in the browser for the same reason the department
 * list is: the catalogue is a closed set with a `CHECK` constraint behind it,
 * and a second copy in TypeScript is a second thing to keep in step. It also
 * carries `connectable` per tool — false for all nine today — so the screen
 * stops promising a later connect flow on the day one actually arrives.
 */
export async function GET(request: Request) {
  return proxyToApi(request, {
    path: '/onboarding/agent/tools',
    method: 'GET',
    unavailable: 'Cannot reach the onboarding service right now.',
  })
}

/**
 * Declare which systems this company runs on. The last step before assembly.
 *
 * `providers` is normalised to an array of strings here so that a malformed
 * body reaches the API as an empty declaration rather than as a 422 about a
 * type — the API validates the ids themselves against its catalogue, which is
 * the check that matters and the one this cannot do.
 */
export async function POST(request: Request) {
  const body = await readJson(request)
  const providers = Array.isArray(body?.providers)
    ? body.providers.filter((id): id is string => typeof id === 'string')
    : []

  return proxyToApi(request, {
    path: '/onboarding/agent/tools',
    method: 'POST',
    body: { providers, skipped: body?.skipped === true },
    unavailable: 'Cannot reach the onboarding service right now.',
  })
}
