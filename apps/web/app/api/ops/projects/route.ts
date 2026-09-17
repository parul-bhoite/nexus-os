import { NextResponse } from 'next/server'
import { proxyToApi, readJson } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * Record a project.
 *
 * **The first POST in this app that writes a customer's own record.** Every
 * other one asks the product to do something; this one stores something a
 * person typed and expects back.
 *
 * Named fields, not a spread — this directory's standing rule. A spread would
 * forward `workspace_id` or `created_by` if a client ever sent them, and while
 * the API sets both from the session regardless, the rule exists so that stays
 * true without anyone having to check the handler to know it.
 */
export async function POST(request: Request) {
  const body = await readJson(request)
  if (!body) return NextResponse.json({ detail: 'Invalid request.' }, { status: 400 })

  return proxyToApi(request, {
    path: '/ops/projects',
    method: 'POST',
    body: {
      name: body.name,
      status: body.status,
      client: body.client ?? null,
      due_on: body.due_on ?? null,
    },
    unavailable: 'Cannot reach the workspace service right now.',
  })
}
