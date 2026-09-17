import { NextResponse } from 'next/server'
import { proxyToApi, readJson } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/** Record a stock line and the minimum to hold — `doc/15` S10.5. */
export async function POST(request: Request) {
  const body = await readJson(request)
  if (!body) return NextResponse.json({ detail: 'Invalid request.' }, { status: 400 })

  return proxyToApi(request, {
    path: '/ops/stock',
    method: 'POST',
    body: {
      name: body.name,
      on_hand: body.on_hand,
      minimum: body.minimum,
      unit: body.unit ?? null,
    },
    unavailable: 'Cannot reach the workspace service right now.',
  })
}
