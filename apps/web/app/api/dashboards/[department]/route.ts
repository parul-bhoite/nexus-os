import { NextResponse } from 'next/server'
import { proxyToApi } from '@/lib/auth-proxy'
import { DEPARTMENTS } from '@/lib/departments'

export const dynamic = 'force-dynamic'

export async function GET(request: Request, { params }: { params: { department: string } }) {
  // Checked before interpolation, for the same reason the invitation id is: an
  // unvalidated segment lets a caller append their own path and reach an
  // endpoint this route was never meant to expose.
  if (!DEPARTMENTS.has(params.department)) {
    return NextResponse.json({ detail: 'Not found.' }, { status: 404 })
  }

  return proxyToApi(request, {
    path: `/dashboards/${params.department}`,
    method: 'GET',
    unavailable: 'Cannot reach the dashboard service right now.',
  })
}
