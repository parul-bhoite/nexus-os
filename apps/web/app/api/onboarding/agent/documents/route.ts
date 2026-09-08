import { proxyToApi, readJson } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * Leave the documents step of onboarding.
 *
 * **Not the upload.** Files go to `/api/documents`, which is a multipart proxy
 * and a different shape of request entirely. This is the person saying they are
 * finished with the step, and keeping the two apart is what lets somebody
 * upload a fourth file after uploading three — folding them together would mean
 * the last upload also closed the step behind them.
 *
 * The body carries only whether they skipped, and the API treats that as a
 * record rather than a permission: the step is skippable either way, so nothing
 * here decides whether the phase advances.
 */
export async function POST(request: Request) {
  const body = await readJson(request)
  return proxyToApi(request, {
    path: '/onboarding/agent/documents',
    method: 'POST',
    body: { skipped: body?.skipped === true },
    unavailable: 'Cannot reach the onboarding service right now.',
  })
}
