import { NextResponse } from 'next/server'
import { proxyToApi } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

/**
 * Mint a short-lived signed URL for a document this caller uploaded.
 *
 * Returns the URL rather than the bytes, and the distinction is the whole
 * design: authorisation happens **here, once**, against the uploader, and the
 * signature that follows proves only that we issued the link and that it has
 * not expired. `/files` then serves it with no session at all — which is the
 * same contract that will hold against S3, where the bytes never pass through
 * us.
 *
 * The URL that comes back is relative (`/files/…`), so the browser resolves it
 * against this app. `app/files/[...key]/route.ts` is what answers it.
 */
export async function GET(request: Request, { params }: { params: { documentId: string } }) {
  if (!UUID.test(params.documentId)) {
    return NextResponse.json({ detail: 'Not found.' }, { status: 404 })
  }

  return proxyToApi(request, {
    path: `/documents/${params.documentId}/download`,
    method: 'GET',
    unavailable: 'Cannot reach the document service right now.',
  })
}
