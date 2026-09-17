import { NextResponse } from 'next/server'
import { proxyToApi, readJson } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * Confirm that an entity's list is all of them — `doc/15` S10.2, ADR 0035.
 *
 * A POST rather than a PUT, and it appends rather than replaces: the question
 * is asked again as the business changes, and the history of when somebody last
 * vouched for the record is the half that carries the doubt.
 *
 * `complete_as_of` is forwarded as given, including `null` — the API defaults it
 * to today. Defaulting it here as well would put two clocks on the same fact,
 * and the browser's is the one nobody can audit.
 */
export async function POST(request: Request) {
  const body = await readJson(request)
  if (!body) return NextResponse.json({ detail: 'Invalid request.' }, { status: 400 })

  return proxyToApi(request, {
    path: '/ops/completeness',
    method: 'POST',
    body: { entity: body.entity, complete_as_of: body.complete_as_of ?? null },
    unavailable: 'Cannot reach the workspace service right now.',
  })
}
