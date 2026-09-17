import { NextResponse } from 'next/server'
import { proxyToApi } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

const PROVIDERS = new Set(['hubspot'])

/**
 * Finish an authorisation the vendor has just sent the browser back from.
 *
 * **The query string is forwarded whole and deliberately.** `code` and `state`
 * are the vendor's and the API verifies both — `state` is signed and bound to
 * workspace, person and provider, so rewriting or re-signing anything here would
 * put this proxy inside a security check that belongs in one place.
 */
export async function GET(request: Request, { params }: { params: { provider: string } }) {
  if (!PROVIDERS.has(params.provider)) {
    return NextResponse.json({ detail: 'Not found.' }, { status: 404 })
  }

  const query = new URL(request.url).search
  return proxyToApi(request, {
    path: `/connections/${params.provider}/callback${query}`,
    method: 'GET',
    unavailable: 'Cannot reach the connection service right now.',
  })
}
