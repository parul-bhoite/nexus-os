import { NextResponse } from 'next/server'
import { proxyToApi } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

/** A real delete, unlike every other record here: `crm_deal` is a sync target
 *  and has no `archived_at` for a read to filter on. */
export async function DELETE(request: Request, { params }: { params: { dealId: string } }) {
  if (!UUID.test(params.dealId)) {
    return NextResponse.json({ detail: 'Not found.' }, { status: 404 })
  }

  return proxyToApi(request, {
    path: `/ops/deals/${params.dealId}`,
    method: 'DELETE',
    unavailable: 'Cannot reach the workspace service right now.',
  })
}
