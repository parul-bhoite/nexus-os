import { NextResponse } from 'next/server'
import { proxyToApi } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/** Only providers the API has wiring for. Checked before interpolation — not the
 *  security boundary, which is the API's, but it keeps an unknown name a 404
 *  here rather than a round trip. */
const PROVIDERS = new Set(['hubspot'])

/**
 * Begin an authorisation and hand back where to send the browser.
 *
 * A POST because it mints signed state, and the API returns the URL rather than
 * redirecting: a 307 to a third party would be followed by this `fetch` instead
 * of by the person.
 */
export async function POST(request: Request, { params }: { params: { provider: string } }) {
  if (!PROVIDERS.has(params.provider)) {
    return NextResponse.json({ detail: 'Not found.' }, { status: 404 })
  }

  return proxyToApi(request, {
    path: `/connections/${params.provider}/authorize`,
    method: 'POST',
    unavailable: 'Cannot reach the connection service right now.',
  })
}
