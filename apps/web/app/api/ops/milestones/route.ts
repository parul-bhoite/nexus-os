import { NextResponse } from 'next/server'
import { proxyToApi, readJson } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/** Record a milestone — `doc/15` S10.3. Named fields, not a spread: this
 *  directory's standing rule. */
export async function POST(request: Request) {
  const body = await readJson(request)
  if (!body) return NextResponse.json({ detail: 'Invalid request.' }, { status: 400 })

  return proxyToApi(request, {
    path: '/ops/milestones',
    method: 'POST',
    body: {
      title: body.title,
      project_id: body.project_id,
      planned_on: body.planned_on,
      status: body.status,
    },
    unavailable: 'Cannot reach the workspace service right now.',
  })
}
