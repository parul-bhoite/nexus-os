import { NextResponse } from 'next/server'
import { proxyToApi } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

const PROVIDERS = new Set(['hubspot'])

/** Disconnect. The tile it fed returns to `locked` rather than to a zero — an
 *  absence, not a measurement of nothing (I10). */
export async function POST(request: Request, { params }: { params: { provider: string } }) {
  if (!PROVIDERS.has(params.provider)) {
    return NextResponse.json({ detail: 'Not found.' }, { status: 404 })
  }

  return proxyToApi(request, {
    path: `/connections/${params.provider}/revoke`,
    method: 'POST',
    unavailable: 'Cannot reach the connection service right now.',
  })
}
