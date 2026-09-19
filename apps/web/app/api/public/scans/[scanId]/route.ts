import { NextResponse } from 'next/server'
import { proxyToApi } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

/** Read one scan result. Anonymous — anyone holding the id can read it,
 * which is intended (`doc/18` §3): the scan is domain-keyed, not
 * visitor-keyed, and bounding who may *fetch* is what the rate limits are
 * for, not this route. */
export async function GET(request: Request, { params }: { params: { scanId: string } }) {
  if (!UUID.test(params.scanId)) {
    return NextResponse.json({ detail: 'Not found.' }, { status: 404 })
  }

  return proxyToApi(request, {
    path: `/public/scans/${params.scanId}`,
    method: 'GET',
    unavailable: 'Cannot reach the scan service right now.',
  })
}

/** Delete a scan result. Soft, idempotent — no session, so no ownership
 * check beyond holding the id (`doc/18` G7's own contract for the route). */
export async function DELETE(request: Request, { params }: { params: { scanId: string } }) {
  if (!UUID.test(params.scanId)) {
    return NextResponse.json({ detail: 'Not found.' }, { status: 404 })
  }

  return proxyToApi(request, {
    path: `/public/scans/${params.scanId}`,
    method: 'DELETE',
    unavailable: 'Cannot reach the scan service right now.',
  })
}
