import { proxyToApi } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * Save a wizard step's answers.
 *
 * The body is `{ answers: [{ key, value }, …] }` and nothing else — no scope
 * field, ever. Each answer's classification and owning department are looked up
 * server-side from the catalogue by its `key` (`app/routes/setup.py`), so the
 * browser cannot widen where an answer lands by what it posts.
 */
export async function POST(request: Request) {
  return proxyToApi(request, {
    path: '/onboarding/answers',
    method: 'POST',
    body: await request.json(),
    unavailable: 'Cannot reach the onboarding service right now.',
  })
}
