import { NextResponse } from 'next/server'
import { proxyToApi } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/** A UUID, checked before interpolation. Not the security boundary — the API
 *  validates it and RLS scopes it — but it keeps a malformed id a 404 here
 *  rather than a round trip, the same rule the department routes follow. */
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

/**
 * Archive a project.
 *
 * `DELETE` sets `archived_at`; nothing is removed. A project that vanished
 * would take its tasks with it, and somebody who archived one by accident would
 * have no way back.
 */
export async function DELETE(request: Request, { params }: { params: { projectId: string } }) {
  if (!UUID.test(params.projectId)) {
    return NextResponse.json({ detail: 'Not found.' }, { status: 404 })
  }

  return proxyToApi(request, {
    path: `/ops/projects/${params.projectId}`,
    method: 'DELETE',
    unavailable: 'Cannot reach the workspace service right now.',
  })
}
