import { MODEL_TIMEOUT_MS, proxyToApi } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * Confirm the brief, correcting any line. A correction outranks the crawl.
 */
export async function POST(request: Request) {
  return proxyToApi(request, {
    path: '/onboarding/agent/brief',
    method: 'POST',
    body: await request.json(),
    unavailable: 'Cannot reach the onboarding service right now.',
    // This route invokes a skill. The default is sized for a database
    // read and aborts mid-call on a slow one.
    timeoutMs: MODEL_TIMEOUT_MS,
  })
}
