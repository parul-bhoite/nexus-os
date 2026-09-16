import { NextResponse } from 'next/server'
import { MODEL_TIMEOUT_MS, proxyToApi, readJson } from '@/lib/auth-proxy'
import { DEPARTMENTS } from '@/lib/departments'

export const dynamic = 'force-dynamic'

/**
 * Ask a director to explain one figure in a sentence.
 *
 * The only POST under `/api/dashboards`, and the only route here that costs
 * money — which is why it is a POST at all. A GET that spent tokens would break
 * the promise `require_csrf` relies on when it exempts safe methods, and a page
 * load that quietly billed for seven sentences nobody asked for is the version
 * of this feature that cannot be taken back.
 *
 * `MODEL_TIMEOUT_MS` rather than the default. A narration is up to two model
 * calls plus a ledger write; on the 30-second database default the proxy would
 * abort a request the API is still working on and tell the founder we could not
 * reach a service that was busy answering them. That message was written to be
 * true, so the timeout has to be long enough for it to stay true.
 *
 * The department is checked against the same set the sibling routes use, before
 * any interpolation. The API checks it again, and checks that the body's
 * capability belongs to it — this check is not the security boundary, it is
 * what keeps an unknown department a 404 here rather than a round trip.
 */
export async function POST(
  request: Request,
  { params }: { params: { department: string } },
) {
  if (!DEPARTMENTS.has(params.department)) {
    return NextResponse.json({ detail: 'Not found.' }, { status: 404 })
  }

  const body = await readJson(request)
  if (!body) return NextResponse.json({ detail: 'Invalid request.' }, { status: 400 })

  return proxyToApi(request, {
    path: `/dashboards/${params.department}/narrate`,
    method: 'POST',
    // One named field, not a spread — this file's standing rule. The capability
    // id is the whole request, and the API validates it against the department
    // in the path rather than trusting either half.
    body: { key: body.key },
    timeoutMs: MODEL_TIMEOUT_MS,
    unavailable: 'Cannot reach the dashboard service right now.',
  })
}
