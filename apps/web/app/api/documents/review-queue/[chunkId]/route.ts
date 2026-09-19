import { NextResponse } from 'next/server'
import { proxyToApi, readJson } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

/**
 * Approve or reject one withheld chunk.
 *
 * The id is shape-checked here so a malformed one is a 404 from this app rather
 * than a 422 from the API — the same guard `public/scans/[scanId]` makes, for
 * the same reason: a path segment that cannot be a chunk id has no business
 * reaching the service.
 *
 * **What this route deliberately does not do is decide anything.** Whether the
 * caller may grant the scope they asked for is `may_reach_scope`'s call, made
 * in the API against the session's real authority — which this app does not
 * hold and must not approximate. A 403 from there is forwarded intact so the
 * screen can show the API's own sentence instead of a guess at one.
 */
export async function POST(request: Request, { params }: { params: { chunkId: string } }) {
  if (!UUID.test(params.chunkId)) {
    return NextResponse.json({ detail: 'Not found.' }, { status: 404 })
  }

  const body = await readJson(request)
  return proxyToApi(request, {
    path: `/documents/review-queue/${params.chunkId}`,
    method: 'POST',
    body: body ?? {},
    unavailable: 'Cannot reach the document service right now.',
  })
}
