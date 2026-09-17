import { NextResponse } from 'next/server'
import { proxyToApi, readJson } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/** Record an order and what it was promised for — `doc/15` S10.4. */
export async function POST(request: Request) {
  const body = await readJson(request)
  if (!body) return NextResponse.json({ detail: 'Invalid request.' }, { status: 400 })

  return proxyToApi(request, {
    path: '/ops/dispatches',
    method: 'POST',
    body: {
      reference: body.reference,
      promised_on: body.promised_on,
      dispatched_on: body.dispatched_on ?? null,
      project_id: body.project_id ?? null,
    },
    unavailable: 'Cannot reach the workspace service right now.',
  })
}
