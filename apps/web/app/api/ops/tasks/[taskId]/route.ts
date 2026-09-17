import { NextResponse } from 'next/server'
import { proxyToApi } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

/** Archive a task. Same rule as its sibling: it stops counting without ceasing
 *  to exist. */
export async function DELETE(request: Request, { params }: { params: { taskId: string } }) {
  if (!UUID.test(params.taskId)) {
    return NextResponse.json({ detail: 'Not found.' }, { status: 404 })
  }

  return proxyToApi(request, {
    path: `/ops/tasks/${params.taskId}`,
    method: 'DELETE',
    unavailable: 'Cannot reach the workspace service right now.',
  })
}
