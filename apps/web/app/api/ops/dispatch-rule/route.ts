import { NextResponse } from 'next/server'
import { proxyToApi, readJson } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * Say when an order counts as late — D32.
 *
 * The first `PUT` through this proxy. It is a single workspace-level rule with
 * one current value, so replacing it is the whole operation; the records under
 * `/api/ops` have no update route at all, for the reason their module docstring
 * gives.
 */
export async function PUT(request: Request) {
  const body = await readJson(request)
  if (!body) return NextResponse.json({ detail: 'Invalid request.' }, { status: 400 })

  return proxyToApi(request, {
    path: '/ops/dispatch-rule',
    method: 'PUT',
    body: { grace_days: body.grace_days },
    unavailable: 'Cannot reach the workspace service right now.',
  })
}
