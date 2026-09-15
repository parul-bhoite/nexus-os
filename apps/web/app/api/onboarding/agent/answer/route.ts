import { MODEL_TIMEOUT_MS, proxyToApi } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * Answer the outstanding question. The body carries text and nothing else — the field it belongs to is read server-side from the agent's last turn.
 */
export async function POST(request: Request) {
  return proxyToApi(request, {
    path: '/onboarding/agent/answer',
    method: 'POST',
    body: await request.json(),
    unavailable: 'Cannot reach the onboarding service right now.',
    // This route invokes a skill. The default is sized for a database
    // read and aborts mid-call on a slow one.
    timeoutMs: MODEL_TIMEOUT_MS,
  })
}
