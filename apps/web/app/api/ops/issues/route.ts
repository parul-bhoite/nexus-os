import { NextResponse } from 'next/server'
import { proxyToApi, readJson } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/** Record an issue or snag — `doc/15` S10.3. */
export async function POST(request: Request) {
  const body = await readJson(request)
  if (!body) return NextResponse.json({ detail: 'Invalid request.' }, { status: 400 })

  return proxyToApi(request, {
    path: '/ops/issues',
    method: 'POST',
    body: {
      title: body.title,
      status: body.status,
      severity: body.severity,
      project_id: body.project_id ?? null,
      due_on: body.due_on ?? null,
    },
    unavailable: 'Cannot reach the workspace service right now.',
  })
}
