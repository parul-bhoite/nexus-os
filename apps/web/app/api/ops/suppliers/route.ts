import { NextResponse } from 'next/server'
import { proxyToApi, readJson } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/** Record a supplier and what you spend with them — `doc/15` S10.5. The spend
 *  is a figure; the share is what NEXUS works out from it. */
export async function POST(request: Request) {
  const body = await readJson(request)
  if (!body) return NextResponse.json({ detail: 'Invalid request.' }, { status: 400 })

  return proxyToApi(request, {
    path: '/ops/suppliers',
    method: 'POST',
    body: {
      name: body.name,
      spend_minor: body.spend_minor ?? null,
      category: body.category ?? null,
    },
    unavailable: 'Cannot reach the workspace service right now.',
  })
}
