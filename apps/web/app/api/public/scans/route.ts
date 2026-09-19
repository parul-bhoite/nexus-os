import { NextResponse } from 'next/server'
import { clientAddress } from '@/lib/client-address'
import { proxyToApi, readJson } from '@/lib/auth-proxy'

export const dynamic = 'force-dynamic'

/**
 * The anonymous Instant Gap Analysis scan. ADR 0046, `doc/18` G8.
 *
 * **The only BFF route that forwards `clientAddress(request)`.** Every other
 * proxy here relies on the session cookie; this one has none, and the API's
 * per-IP rate limit (`app.scan.client_address.client_ip`) needs an address
 * to key by — the same reasoning that restored `client-address.ts` in the
 * first place.
 */
export async function POST(request: Request) {
  const body = await readJson(request)
  if (!body || typeof body.url !== 'string') {
    return NextResponse.json({ detail: 'A website address is required.' }, { status: 400 })
  }

  return proxyToApi(request, {
    path: '/public/scans',
    method: 'POST',
    body: { url: body.url },
    headers: clientAddress(request),
    unavailable: 'Cannot reach the scan service right now.',
  })
}
