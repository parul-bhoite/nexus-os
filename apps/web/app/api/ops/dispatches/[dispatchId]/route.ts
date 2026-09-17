import { NextResponse } from 'next/server'
import { proxyToApi } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

/** Archive an order. */
export async function DELETE(request: Request, { params }: { params: { dispatchId: string } }) {
  if (!UUID.test(params.dispatchId)) {
    return NextResponse.json({ detail: 'Not found.' }, { status: 404 })
  }

  return proxyToApi(request, {
    path: `/ops/dispatches/${params.dispatchId}`,
    method: 'DELETE',
    unavailable: 'Cannot reach the workspace service right now.',
  })
}
