import { NextResponse } from 'next/server'
import { proxyToApi, readJson } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/** Record a deal by hand — `doc/15` S10.6. Written as `provider = 'nexus'` so it
 *  never reaches the CRM pipeline figure (ADR 0038). */
export async function POST(request: Request) {
  const body = await readJson(request)
  if (!body) return NextResponse.json({ detail: 'Invalid request.' }, { status: 400 })

  return proxyToApi(request, {
    path: '/ops/deals',
    method: 'POST',
    body: {
      name: body.name,
      amount_minor: body.amount_minor ?? null,
      currency: body.currency ?? null,
      stage: body.stage ?? null,
      closes_on: body.closes_on ?? null,
    },
    unavailable: 'Cannot reach the workspace service right now.',
  })
}
