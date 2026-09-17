import { NextResponse } from 'next/server'
import { proxyToApi } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

export async function DELETE(request: Request, { params }: { params: { supplierId: string } }) {
  if (!UUID.test(params.supplierId)) {
    return NextResponse.json({ detail: 'Not found.' }, { status: 404 })
  }

  return proxyToApi(request, {
    path: `/ops/suppliers/${params.supplierId}`,
    method: 'DELETE',
    unavailable: 'Cannot reach the workspace service right now.',
  })
}
