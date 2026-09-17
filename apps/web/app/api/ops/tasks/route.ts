import { NextResponse } from 'next/server'
import { proxyToApi, readJson } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/** Record a task. `project_id` is optional and the API refuses one belonging to
 *  another workspace with a 404, so nothing here needs to know about projects. */
export async function POST(request: Request) {
  const body = await readJson(request)
  if (!body) return NextResponse.json({ detail: 'Invalid request.' }, { status: 400 })

  return proxyToApi(request, {
    path: '/ops/tasks',
    method: 'POST',
    body: {
      title: body.title,
      status: body.status,
      project_id: body.project_id ?? null,
      due_on: body.due_on ?? null,
    },
    unavailable: 'Cannot reach the workspace service right now.',
  })
}
